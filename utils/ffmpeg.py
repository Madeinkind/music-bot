"""Поиск рабочего бинарника ffmpeg."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    """ffmpeg не найден или не запускается."""


def _is_working(path: str) -> bool:
    try:
        result = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def resolve_ffmpeg(explicit: str | None = None) -> str:
    """Возвращает путь к ffmpeg: аргумент → FFMPEG_PATH → PATH → imageio-ffmpeg."""

    candidates: list[str] = []
    for value in (explicit, os.getenv("FFMPEG_PATH")):
        if not value:
            continue
        expanded = str(Path(value).expanduser())
        found = shutil.which(expanded) or (expanded if Path(expanded).is_file() else None)
        if found is None:
            raise FFmpegError(f"FFMPEG_PATH указывает на несуществующий файл: {value}")
        candidates.append(found)

    system = shutil.which("ffmpeg")
    if system:
        candidates.append(system)

    if not candidates:
        try:
            import imageio_ffmpeg

            candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception:  # imageio-ffmpeg не установлен или не смог скачать бинарник
            log.debug("imageio-ffmpeg недоступен", exc_info=True)

    for candidate in candidates:
        if _is_working(candidate):
            log.info("Использую ffmpeg: %s", candidate)
            return candidate

    raise FFmpegError(
        "ffmpeg не найден. Варианты:\n"
        "  1) Windows: winget install Gyan.FFmpeg\n"
        "  2) Linux: sudo apt install ffmpeg\n"
        "  3) pip install imageio-ffmpeg (запасной вариант)\n"
        "  4) указать путь вручную: FFMPEG_PATH=C:\\ffmpeg\\bin\\ffmpeg.exe"
    )
