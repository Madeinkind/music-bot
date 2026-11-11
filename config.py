"""Загрузка и проверка конфигурации бота из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Некорректная конфигурация бота."""


def _get_raw(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _get_int(name: str, default: int, *, minimum: int, maximum: int | None = None) -> int:
    raw = _get_raw(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"Переменная {name} должна быть целым числом, получено: {raw!r}") from exc
    if value < minimum:
        raise ConfigError(f"Переменная {name} не может быть меньше {minimum}")
    if maximum is not None and value > maximum:
        raise ConfigError(f"Переменная {name} не может быть больше {maximum}")
    return value


def _get_optional_int(name: str) -> int | None:
    raw = _get_raw(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Переменная {name} должна быть числом (ID сервера), получено: {raw!r}") from exc


def _get_bool(name: str, default: bool) -> bool:
    raw = _get_raw(name)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in {"1", "true", "yes", "on", "да"}:
        return True
    if lowered in {"0", "false", "no", "off", "нет"}:
        return False
    raise ConfigError(f"Переменная {name} должна быть true или false, получено: {raw!r}")


def _get_color(name: str, default: int) -> int:
    raw = _get_raw(name)
    if raw is None:
        return default
    try:
        value = int(raw, 0)
    except ValueError as exc:
        raise ConfigError(f"Переменная {name} должна быть цветом вида 0x5865F2, получено: {raw!r}") from exc
    if not 0 <= value <= 0xFFFFFF:
        raise ConfigError(f"Переменная {name} должна быть в диапазоне 0x000000–0xFFFFFF")
    return value


@dataclass(frozen=True, slots=True)
class Config:
    """Настройки бота."""

    token: str
    prefix: str = "!"
    dev_guild_id: int | None = None
    ffmpeg_path: str | None = None
    cookies_file: str | None = None
    proxy: str | None = None
    default_volume: int = 60
    max_queue_size: int = 500
    max_playlist_items: int = 100
    idle_timeout: int = 300
    embed_color: int = 0x5865F2
    log_level: str = "INFO"
    self_deaf: bool = True


def load_config() -> Config:
    """Читает настройки из окружения и валидирует их."""

    token = _get_raw("DISCORD_TOKEN")
    if token is None:
        raise ConfigError(
            "Не задан DISCORD_TOKEN. Скопируйте .env.example в .env и вставьте токен бота "
            "(Discord Developer Portal -> ваше приложение -> Bot -> Reset Token)."
        )

    log_level = (_get_raw("LOG_LEVEL") or "INFO").upper()
    if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
        raise ConfigError(
            f"Неизвестный LOG_LEVEL: {log_level!r}. "
            "Допустимо: DEBUG, INFO, WARNING, ERROR, CRITICAL."
        )

    return Config(
        token=token,
        prefix=_get_raw("COMMAND_PREFIX") or "!",
        dev_guild_id=_get_optional_int("DEV_GUILD_ID"),
        ffmpeg_path=_get_raw("FFMPEG_PATH"),
        cookies_file=_get_raw("YTDL_COOKIES_FILE"),
        proxy=_get_raw("PROXY"),
        default_volume=_get_int("DEFAULT_VOLUME", 60, minimum=0, maximum=200),
        max_queue_size=_get_int("MAX_QUEUE_SIZE", 500, minimum=1, maximum=10_000),
        max_playlist_items=_get_int("MAX_PLAYLIST_ITEMS", 100, minimum=1, maximum=1_000),
        idle_timeout=_get_int("IDLE_TIMEOUT", 300, minimum=0, maximum=86_400),
        embed_color=_get_color("EMBED_COLOR", 0x5865F2),
        log_level=log_level,
        self_deaf=_get_bool("SELF_DEAF", True),
    )
