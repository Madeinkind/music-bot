"""Плеер на один сервер: очередь, голосовое подключение и воспроизведение."""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from typing import TYPE_CHECKING, Any

import discord

from music.errors import MusicError, VoiceError
from music.queue import Queue, QueueFull
from music.track import Track
from utils import embeds
from utils.formatting import format_duration

if TYPE_CHECKING:
    from bot import MusicBot

log = logging.getLogger(__name__)

FFMPEG_BEFORE_OPTIONS = "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"


class LoopMode(enum.StrEnum):
    """Режим повтора."""

    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"

    @property
    def label(self) -> str:
        return {"off": "выключен", "track": "трек", "queue": "очередь"}[self.value]

    def next(self) -> LoopMode:
        order = (LoopMode.OFF, LoopMode.TRACK, LoopMode.QUEUE)
        return order[(order.index(self) + 1) % len(order)]


class MusicPlayer:
    """Состояние и логика воспроизведения для одного сервера."""

    def __init__(
        self,
        bot: MusicBot,
        guild: discord.Guild,
        text_channel: discord.abc.Messageable | None = None,
    ) -> None:
        self.bot = bot
        self.guild = guild
        self.text_channel = text_channel
        self.queue = Queue(bot.config.max_queue_size)
        self.current: Track | None = None
        self.voice: discord.VoiceClient | None = None
        self.loop_mode = LoopMode.OFF

        self._volume = bot.config.default_volume
        self._generation = 0
        self._lock = asyncio.Lock()
        self._idle_task: asyncio.Task[None] | None = None
        self._playing_since = 0.0
        self._paused_at: float | None = None
        self._offset = 0

    # ------------------------------------------------------------------ состояние

    @property
    def volume(self) -> int:
        return self._volume

    @property
    def is_playing(self) -> bool:
        return bool(self.voice and (self.voice.is_playing() or self.voice.is_paused()))

    @property
    def is_connected(self) -> bool:
        return bool(self.voice and self.voice.is_connected())

    @property
    def position(self) -> int:
        """Текущая позиция трека в секундах."""

        if self.current is None:
            return 0
        elapsed = float(self._offset)
        if self.voice is not None and self.voice.is_playing():
            elapsed += max(0.0, time.time() - self._playing_since)
        elif self.voice is not None and self.voice.is_paused() and self._paused_at is not None:
            elapsed += max(0.0, self._paused_at - self._playing_since)
        if self.current.duration:
            return int(min(elapsed, self.current.duration))
        return int(elapsed)

    def set_volume(self, volume: int) -> int:
        self._volume = max(0, min(200, int(volume)))
        source = self.voice.source if self.voice else None
        if isinstance(source, discord.PCMVolumeTransformer):
            source.volume = self._volume / 100
        return self._volume

    # ------------------------------------------------------------------ подключение

    async def connect(self, channel: discord.VoiceChannel) -> None:
        if self.is_connected:
            if self.voice is not None and self.voice.channel != channel:
                await self.voice.move_to(channel)
            return
        try:
            self.voice = await channel.connect(self_deaf=True, timeout=20.0)
        except TimeoutError as exc:
            raise VoiceError("Не удалось подключиться к голосовому каналу (таймаут).") from exc
        except discord.ClientException as exc:
            raise VoiceError(f"Не удалось подключиться к каналу: {exc}") from exc
        self._cancel_idle()

    async def disconnect(self) -> None:
        self._cancel_idle()
        self._generation += 1
        self.current = None
        self.queue.clear()
        self.loop_mode = LoopMode.OFF
        self._offset = 0
        voice, self.voice = self.voice, None
        if voice is not None:
            try:
                await voice.disconnect(force=True)
            except Exception:  # уже отключён / канал удалён
                log.debug("Ошибка при отключении от канала", exc_info=True)
        self.bot.players.pop(self.guild.id, None)

    def cleanup(self) -> None:
        """Сброс состояния без обращения к Discord (например, бота выгнали)."""

        self._cancel_idle()
        self._generation += 1
        self.current = None
        self.queue.clear()
        self.loop_mode = LoopMode.OFF
        self.voice = None
        self._offset = 0
        self.bot.players.pop(self.guild.id, None)

    # ------------------------------------------------------------------ очередь

    def enqueue(self, tracks: list[Track]) -> tuple[int, int]:
        added = self.queue.add_many(tracks)
        return added, len(tracks) - added

    # ------------------------------------------------------------------ воспроизведение

    async def play_next(self) -> bool:
        """Останавливает текущий трек и запускает следующий из очереди."""

        self._generation += 1
        if self.voice is not None and (self.voice.is_playing() or self.voice.is_paused()):
            self.voice.stop()
        async with self._lock:
            return await self._play_next_locked()

    async def _play_next_locked(self) -> bool:
        while self.queue:
            track = self.queue.pop()
            if track is None:
                break
            track.reset_playback_state()
            self._offset = 0
            try:
                stream_url = await self.bot.ytdl.get_stream_url(track)
            except MusicError as exc:
                log.warning("Не удалось загрузить %s: %s", track.webpage_url, exc)
                await self._send(embeds.error(f"Пропускаю «{track.title}»: {exc}"))
                continue

            if not self.is_connected:
                await self._send(embeds.error("Бот не подключён к голосовому каналу. Используйте `/join`."))
                self._schedule_idle()
                return False

            self.current = track
            self._start_track(track, stream_url)
            self._cancel_idle()
            await self._send(embeds.now_playing_embed(track, self), view=self._now_playing_view())
            return True

        self.current = None
        await self._send(embeds.info("Очередь закончилась. Добавьте треки командой `/play`."))
        self._schedule_idle()
        return False

    def _now_playing_view(self) -> Any:
        # Импорт внутри метода, чтобы не было циклической зависимости модулей.
        from music.views import NowPlayingView

        return NowPlayingView(self)

    def _start_track(self, track: Track, stream_url: str) -> None:
        if self.voice is None:
            raise VoiceError("Нет голосового подключения.")

        self._generation += 1
        generation = self._generation

        before_options = FFMPEG_BEFORE_OPTIONS
        if track.start_offset > 0 and not track.is_live:
            before_options += f" -ss {int(track.start_offset)}"

        source: discord.AudioSource = discord.FFmpegPCMAudio(
            stream_url,
            executable=self.bot.ffmpeg_path,
            before_options=before_options,
            options="-vn",
        )
        source = discord.PCMVolumeTransformer(source, volume=self._volume / 100)
        self.voice.play(source, after=lambda err, gen=generation: self._after_track(gen, err))
        self._playing_since = time.time()
        self._paused_at = None

    def _after_track(self, generation: int, error: Exception | None) -> None:
        """Вызывается из потока ffmpeg после окончания трека."""

        if error is not None:
            log.warning("Ошибка воспроизведения: %s", error)
        try:
            future = asyncio.run_coroutine_threadsafe(self._handle_track_end(generation), self.bot.loop)
            future.add_done_callback(self._log_future_error)
        except RuntimeError:  # цикл событий уже закрыт
            pass

    @staticmethod
    def _log_future_error(future: asyncio.Future[Any]) -> None:
        try:
            future.result()
        except Exception:
            log.exception("Ошибка в обработчике окончания трека")

    async def _handle_track_end(self, generation: int) -> None:
        async with self._lock:
            if generation != self._generation:
                return
            finished = self.current
            self.current = None
            if finished is not None:
                finished.start_offset = 0
                if self.loop_mode is LoopMode.TRACK and not finished.is_live:
                    self.queue.add_first(finished)
                elif self.loop_mode is LoopMode.QUEUE:
                    try:
                        self.queue.add(finished)
                    except QueueFull:
                        pass
            await self._play_next_locked()

    # ------------------------------------------------------------------ управление

    def pause(self) -> bool:
        if self.voice is not None and self.voice.is_playing():
            self.voice.pause()
            self._paused_at = time.time()
            return True
        return False

    def resume(self) -> bool:
        if self.voice is not None and self.voice.is_paused():
            self.voice.resume()
            if self._paused_at is not None:
                self._playing_since += time.time() - self._paused_at
                self._paused_at = None
            return True
        return False

    async def skip(self) -> bool:
        if self.current is None and not self.queue:
            return False
        await self.play_next()
        return True

    async def stop(self) -> None:
        self._generation += 1
        self.current = None
        self.queue.clear()
        self.loop_mode = LoopMode.OFF
        self._offset = 0
        if self.voice is not None:
            self.voice.stop()
        self._schedule_idle()

    async def seek(self, seconds: int) -> None:
        track = self.current
        if track is None:
            raise MusicError("Сейчас ничего не играет.")
        if track.is_live:
            raise MusicError("Прямой эфир нельзя перемотать.")
        if seconds < 0:
            raise MusicError("Позиция не может быть отрицательной.")
        if track.duration and seconds >= track.duration:
            raise MusicError(f"Трек длится всего {format_duration(track.duration)}.")
        if not self.is_connected:
            raise MusicError("Бот не подключён к голосовому каналу.")

        was_paused = bool(self.voice and self.voice.is_paused())
        track.start_offset = seconds
        stream_url = await self.bot.ytdl.get_stream_url(track)
        self._offset = seconds

        self._generation += 1
        if self.voice is not None:
            self.voice.stop()
        self._start_track(track, stream_url)
        if was_paused and self.voice is not None:
            self.voice.pause()
            self._paused_at = time.time()

    # ------------------------------------------------------------------ служебное

    async def _send(self, embed: discord.Embed, *, view: discord.ui.View | None = None) -> None:
        if self.text_channel is None:
            return
        try:
            await self.text_channel.send(embed=embed, view=view)
        except (discord.Forbidden, discord.HTTPException):
            log.debug("Не удалось отправить сообщение в канал", exc_info=True)

    def _cancel_idle(self) -> None:
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    def _schedule_idle(self) -> None:
        self._cancel_idle()
        if self.bot.config.idle_timeout <= 0:
            return
        self._idle_task = self.bot.loop.create_task(self._idle_loop())

    async def _idle_loop(self) -> None:
        try:
            await asyncio.sleep(self.bot.config.idle_timeout)
        except asyncio.CancelledError:
            return
        if self.current is None and not self.queue:
            await self._send(embeds.info("Ничего не играет — отключаюсь от канала."))
            await self.disconnect()
