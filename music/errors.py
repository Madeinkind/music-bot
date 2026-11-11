"""Исключения музыкальной части."""

from __future__ import annotations


class MusicError(Exception):
    """Ошибка, текст которой можно показать пользователю."""


class TrackLoadError(MusicError):
    """Не удалось найти или загрузить трек."""


class VoiceError(MusicError):
    """Проблема с голосовым подключением."""
