"""Обёртка над yt-dlp: поиск, плейлисты и прямые ссылки на аудиопоток."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError

from config import Config
from music.errors import TrackLoadError
from music.track import Track
from utils.formatting import truncate

log = logging.getLogger(__name__)

URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# Прямые ссылки googlevideo живут несколько часов, но обновляем их заранее.
STREAM_TTL = 15 * 60
EXTRACT_TIMEOUT = 45.0


def is_url(text: str) -> bool:
    return bool(URL_RE.match(text.strip()))


def is_playlist_url(text: str) -> bool:
    lowered = text.lower()
    return "list=" in lowered or "/playlist" in lowered or "/sets/" in lowered


class YTDLSource:
    """Асинхронная обёртка: тяжёлые вызовы yt-dlp уходят в отдельный поток."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._base_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "noplaylist": False,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "cachedir": False,
            "geo_bypass": True,
            "socket_timeout": 15,
            "retries": 3,
            "default_search": "ytsearch",
            "source_address": "0.0.0.0",
        }

        if config.cookies_file:
            cookies = Path(config.cookies_file).expanduser()
            if not cookies.is_file():
                raise TrackLoadError(f"Файл cookies не найден: {cookies}")
            self._base_opts["cookiefile"] = str(cookies)
            log.info("Использую cookies из %s", cookies)
        if config.proxy:
            self._base_opts["proxy"] = config.proxy

    async def resolve(self, query: str, *, requester: Any, limit: int = 1) -> list[Track]:
        """Ищет треки по запросу или разбирает ссылку (в т.ч. плейлист)."""

        query = query.strip()
        if not query:
            raise TrackLoadError("Пустой запрос — укажите название трека или ссылку.")

        limit = max(1, min(limit, self._config.max_playlist_items))
        target = query if is_url(query) else f"ytsearch{limit}:{query}"

        try:
            info = await asyncio.wait_for(asyncio.to_thread(self._extract, target, limit), EXTRACT_TIMEOUT)
        except TimeoutError as exc:
            raise TrackLoadError("yt-dlp не успел ответить. Попробуйте ещё раз.") from exc
        except DownloadError as exc:
            raise TrackLoadError(self._friendly_error(str(exc))) from exc

        if not info:
            raise TrackLoadError("Ничего не найдено по этому запросу.")

        tracks: list[Track] = []
        for entry in self._entries(info)[:limit]:
            track = self._track_from_entry(entry, requester)
            if track is not None:
                tracks.append(track)
        if not tracks:
            raise TrackLoadError("Не удалось разобрать результат. Возможно, ссылка ведёт на неподдерживаемый ресурс.")
        return tracks

    async def get_stream_url(self, track: Track) -> str:
        """Возвращает свежий прямой адрес аудиопотока."""

        if track.has_fresh_stream() and track.stream_url is not None:
            return track.stream_url

        try:
            stream_url, info = await asyncio.wait_for(
                asyncio.to_thread(self._resolve_stream, track.webpage_url),
                EXTRACT_TIMEOUT,
            )
        except TimeoutError as exc:
            raise TrackLoadError("yt-dlp не успел получить аудиопоток.") from exc
        except DownloadError as exc:
            raise TrackLoadError(self._friendly_error(str(exc))) from exc

        track.stream_url = stream_url
        track.stream_expires_at = time.time() + STREAM_TTL
        if not track.duration and info.get("duration"):
            track.duration = int(info["duration"])
        if not track.uploader:
            track.uploader = info.get("uploader") or info.get("channel")
        return stream_url

    # ------------------------------------------------------------------ синхронная часть

    def _extract(self, target: str, limit: int) -> dict[str, Any] | None:
        opts = dict(self._base_opts)
        opts["playlistend"] = limit
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(target, download=False)

    def _resolve_stream(self, webpage_url: str) -> tuple[str, dict[str, Any]]:
        opts = dict(self._base_opts)
        opts.update(
            {
                "format": "bestaudio/best",
                "extract_flat": False,
                "noplaylist": True,
                "playlistend": 1,
            }
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(webpage_url, download=False)

        if info.get("_type") == "playlist":
            entries = [entry for entry in (info.get("entries") or []) if entry]
            if not entries:
                raise TrackLoadError("Плейлист пуст.")
            info = entries[0]

        stream_url = info.get("url") or self._pick_audio_format(info)
        if not stream_url:
            raise TrackLoadError("Не удалось получить аудиопоток.")
        return stream_url, info

    @staticmethod
    def _pick_audio_format(info: dict[str, Any]) -> str | None:
        formats = info.get("formats") or []
        audio = [
            fmt
            for fmt in formats
            if fmt.get("url") and fmt.get("vcodec") == "none" and fmt.get("acodec") not in (None, "none")
        ]
        if not audio:
            audio = [fmt for fmt in formats if fmt.get("url") and fmt.get("acodec") not in (None, "none")]
        if not audio:
            return None
        audio.sort(key=lambda fmt: fmt.get("abr") or fmt.get("tbr") or 0, reverse=True)
        return audio[0]["url"]

    @staticmethod
    def _entries(info: dict[str, Any]) -> list[dict[str, Any]]:
        if info.get("_type") in ("playlist", "multi_video"):
            return [entry for entry in (info.get("entries") or []) if entry]
        return [info]

    def _track_from_entry(self, entry: dict[str, Any], requester: Any) -> Track | None:
        if not entry:
            return None
        if entry.get("_type") in ("playlist", "multi_video"):
            nested = [item for item in (entry.get("entries") or []) if item]
            return self._track_from_entry(nested[0], requester) if nested else None

        webpage_url = entry.get("webpage_url") or entry.get("original_url")
        url = entry.get("url")
        if isinstance(url, str) and url.startswith("http"):
            webpage_url = webpage_url or url
        if not webpage_url and entry.get("id") and (entry.get("ie_key") or "Youtube") == "Youtube":
            webpage_url = f"https://www.youtube.com/watch?v={entry['id']}"
        if not webpage_url:
            log.debug("Пропускаю запись без ссылки: %s", truncate(str(entry.get("title")), 40))
            return None

        thumbnail = entry.get("thumbnail")
        if not thumbnail:
            thumbnails = [item for item in (entry.get("thumbnails") or []) if item.get("url")]
            if thumbnails:
                thumbnail = thumbnails[-1]["url"]

        return Track(
            title=str(entry.get("title") or "Без названия"),
            webpage_url=webpage_url,
            duration=int(entry.get("duration") or 0),
            requester_id=int(getattr(requester, "id", 0) or 0),
            requester_name=str(
                getattr(requester, "display_name", None)
                or getattr(requester, "name", None)
                or "Неизвестно"
            ),
            thumbnail=thumbnail,
            uploader=entry.get("uploader") or entry.get("channel"),
            is_live=bool(entry.get("is_live")),
        )

    @staticmethod
    def _friendly_error(message: str) -> str:
        lowered = message.lower()
        if "sign in" in lowered or ("bot" in lowered and "confirm" in lowered):
            return (
                "YouTube требует подтвердить, что запрос не от бота. "
                "Укажите cookies браузера в YTDL_COOKIES_FILE — инструкция в README."
            )
        if "age" in lowered and "restrict" in lowered:
            return "Видео с возрастным ограничением. Нужны cookies авторизованного аккаунта (см. README)."
        if "private" in lowered:
            return "Видео приватное — его нельзя воспроизвести."
        if "unavailable" in lowered or "removed" in lowered:
            return "Видео недоступно: удалено, скрыто или заблокировано в регионе."
        if "members-only" in lowered or "join this channel" in lowered:
            return "Видео доступно только участникам канала."
        if "live event" in lowered and "starting" in lowered:
            return "Трансляция ещё не началась."
        return f"yt-dlp: {truncate(message, 200)}"
