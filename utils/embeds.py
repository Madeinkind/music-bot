"""Эмбеды для сообщений бота."""

from __future__ import annotations

from typing import Any

import discord

from music.track import Track
from utils.formatting import format_duration, progress_bar, truncate

COLOR_PRIMARY = 0x5865F2
COLOR_SUCCESS = 0x57F287
COLOR_WARNING = 0xFEE75C
COLOR_ERROR = 0xED4245

QUEUE_PER_PAGE = 10


def _player_color(player: Any) -> int:
    config = getattr(getattr(player, "bot", None), "config", None)
    return getattr(config, "embed_color", COLOR_PRIMARY)


def base(title: str | None = None, description: str | None = None, *, color: int = COLOR_PRIMARY) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


def info(text: str, *, title: str | None = None, color: int = COLOR_PRIMARY) -> discord.Embed:
    return base(title, text, color=color)


def success(text: str, *, title: str = "Готово") -> discord.Embed:
    return base(title, text, color=COLOR_SUCCESS)


def warning(text: str, *, title: str = "Внимание") -> discord.Embed:
    return base(title, text, color=COLOR_WARNING)


def error(text: str, *, title: str = "Ошибка") -> discord.Embed:
    return base(title, text, color=COLOR_ERROR)


def now_playing_embed(track: Track, player: Any) -> discord.Embed:
    embed = base(
        "Сейчас играет",
        f"[{truncate(track.title, 90)}]({track.webpage_url})",
        color=_player_color(player),
    )
    if track.uploader:
        embed.add_field(name="Исполнитель", value=truncate(track.uploader, 60), inline=True)
    embed.add_field(name="Длительность", value=track.duration_text, inline=True)
    embed.add_field(name="Запросил", value=track.requester_mention, inline=True)

    position = getattr(player, "position", 0)
    if track.duration and not track.is_live:
        embed.add_field(
            name="Прогресс",
            value=f"{progress_bar(position, track.duration)}\n`{format_duration(position)} / {track.duration_text}`",
            inline=False,
        )

    loop_mode = getattr(player, "loop_mode", None)
    if loop_mode is not None:
        embed.add_field(name="Повтор", value=getattr(loop_mode, "label", "выключен"), inline=True)
    embed.add_field(name="Громкость", value=f"{getattr(player, 'volume', 100)}%", inline=True)

    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)
    embed.set_footer(text=f"Очередь: {len(getattr(player, 'queue', []))} трек(ов)")
    return embed


def track_line(index: int, track: Track) -> str:
    return (
        f"**{index}.** [{truncate(track.title, 60)}]({track.webpage_url}) "
        f"`{track.duration_text}` — {track.requester_mention}"
    )


def enqueue_embed(tracks: list[Track], player: Any, *, added: int, skipped: int = 0) -> discord.Embed:
    lines = [track_line(index, track) for index, track in enumerate(tracks[:5], start=1)]
    if len(tracks) > 5:
        lines.append(f"…и ещё {len(tracks) - 5} трек(ов)")
    description = "\n".join(lines)
    if added == 1 and tracks:
        title = "Трек добавлен в очередь"
    else:
        title = f"Добавлено треков: {added}"
    if skipped:
        description += f"\n\n⚠️ Не поместилось в очередь: {skipped}"
    if getattr(player, "current", None) is None:
        description += "\n\n▶️ Включаю первый трек."
    return base(title, description, color=_player_color(player))


def search_embed(tracks: list[Track]) -> discord.Embed:
    lines = [track_line(index, track) for index, track in enumerate(tracks, start=1)]
    return base("Результаты поиска", "\n".join(lines))


def queue_embed(player: Any, page: int = 1) -> tuple[discord.Embed, int]:
    queue = player.queue
    tracks, page, pages = queue.page(page, QUEUE_PER_PAGE)
    total = len(queue)
    description: list[str] = []

    current: Track | None = getattr(player, "current", None)
    if current is not None:
        description.append(f"**Сейчас играет:** [{truncate(current.title, 60)}]({current.webpage_url})")
        description.append("")

    if tracks:
        start = (page - 1) * QUEUE_PER_PAGE
        description.extend(track_line(start + index, track) for index, track in enumerate(tracks, start=1))
    elif current is None:
        description.append("Очередь пуста. Добавьте треки командой `/play`.")

    embed = base("Очередь", "\n".join(description), color=_player_color(player))
    embed.set_footer(
        text=(
            f"Треков: {total} • Общее время: {format_duration(queue.total_duration)} "
            f"• Страница {page}/{pages}"
        )
    )
    return embed, pages


def help_embed(prefix: str) -> discord.Embed:
    embed = base(
        "Музыкальный бот",
        f"Префикс команд: `{prefix}` (или упоминание бота). "
        "Все команды также доступны как слэш-команды `/`.",
    )
    groups = {
        "Воспроизведение": [
            ("play <запрос/ссылка>", "Включить трек или плейлист"),
            ("search <запрос>", "Найти и выбрать трек из результатов"),
            ("pause / resume", "Пауза и продолжение"),
            ("skip", "Пропустить текущий трек"),
            ("stop", "Остановить и очистить очередь"),
            ("seek <секунды>", "Перемотать текущий трек"),
        ],
        "Очередь": [
            ("queue", "Показать очередь"),
            ("nowplaying", "Информация о текущем треке"),
            ("remove <номер>", "Удалить трек из очереди"),
            ("clear", "Очистить очередь"),
            ("shuffle", "Перемешать очередь"),
            ("loop [off|track|queue]", "Режим повтора"),
        ],
        "Голосовой канал": [
            ("join", "Подключиться к вашему каналу"),
            ("leave", "Отключиться и очистить очередь"),
            ("volume <0-200>", "Громкость воспроизведения"),
            ("voicecheck", "Диагностика голосового подключения"),
        ],
    }
    for name, entries in groups.items():
        embed.add_field(
            name=name,
            value="\n".join(f"`{command}` — {description}" for command, description in entries),
            inline=False,
        )
    embed.set_footer(text="Пример: !play never gonna give you up")
    return embed
