"""Форматирование значений для сообщений бота."""

from __future__ import annotations


def format_duration(seconds: int | float | None) -> str:
    """1:05 / 12:34 / 1:02:03."""

    if not seconds or seconds <= 0:
        return "0:00"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def progress_bar(position: int, duration: int, length: int = 14) -> str:
    """Полоса прогресса воспроизведения."""

    if duration <= 0:
        return ""
    ratio = min(max(position / duration, 0.0), 1.0)
    filled = min(length, int(round(ratio * length)))
    if filled >= length:
        return "█" * length
    return "█" * filled + "🔘" + "─" * (length - filled - 1)


def truncate(text: str, limit: int = 60) -> str:
    """Обрезает строку, добавляя многоточие."""

    if limit <= 1:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
