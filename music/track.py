"""Модель трека."""

from __future__ import annotations

import time
from dataclasses import dataclass

from utils.formatting import format_duration


@dataclass(slots=True)
class Track:
    """Один трек в очереди.

    ``webpage_url`` — страница трека (по ней yt-dlp получает свежий поток),
    ``stream_url`` — прямой адрес аудиопотока, живёт ограниченное время.
    """

    title: str
    webpage_url: str
    duration: int = 0
    requester_id: int = 0
    requester_name: str = "Неизвестно"
    thumbnail: str | None = None
    uploader: str | None = None
    is_live: bool = False

    stream_url: str | None = None
    stream_expires_at: float = 0.0
    start_offset: int = 0

    @property
    def requester_mention(self) -> str:
        return f"<@{self.requester_id}>" if self.requester_id else self.requester_name

    @property
    def duration_text(self) -> str:
        if self.is_live:
            return "🔴 в эфире"
        return format_duration(self.duration)

    def has_fresh_stream(self) -> bool:
        """Поток ещё не протух и его можно переиспользовать."""

        return bool(self.stream_url) and time.time() < self.stream_expires_at

    def reset_playback_state(self) -> None:
        self.start_offset = 0
