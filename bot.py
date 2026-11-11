"""Точка входа музыкального бота."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config import Config, ConfigError, load_config
from music.ytdl import YTDLSource
from utils.ffmpeg import FFmpegError, resolve_ffmpeg

if TYPE_CHECKING:
    from music.player import MusicPlayer

log = logging.getLogger("musicbot")


class MusicBot(commands.Bot):
    """Бот с общим состоянием: yt-dlp и плееры по серверам."""

    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(
            command_prefix=commands.when_mentioned_or(config.prefix),
            intents=intents,
            help_command=None,
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.config = config
        self.ytdl = YTDLSource(config)
        self.players: dict[int, MusicPlayer] = {}
        self.ffmpeg_path = resolve_ffmpeg(config.ffmpeg_path)
        self.started_at = discord.utils.utcnow()

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.music")
        await self.load_extension("cogs.events")

        if self.config.dev_guild_id:
            guild = discord.Object(id=self.config.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Синхронизировано %d команд для сервера %s", len(synced), self.config.dev_guild_id)
        else:
            synced = await self.tree.sync()
            log.info("Синхронизировано %d глобальных команд", len(synced))

    async def close(self) -> None:
        for player in list(self.players.values()):
            try:
                await player.disconnect()
            except Exception:
                log.debug("Не удалось отключить плеер при остановке", exc_info=True)
        await super().close()


def setup_logging(level: str) -> None:
    # Windows-консоль не умеет в Unicode-символы вроде «→»: заменяем их, а не падаем.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("yt_dlp").setLevel(logging.WARNING)


def main() -> int:
    load_dotenv()
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1

    setup_logging(config.log_level)

    try:
        bot = MusicBot(config)
    except FFmpegError as exc:
        log.error("%s", exc)
        return 1
    except Exception:
        log.exception("Не удалось инициализировать бота")
        return 1

    try:
        bot.run(config.token, log_handler=None)
    except discord.LoginFailure:
        log.error(
            "Discord отклонил токен. Проверьте DISCORD_TOKEN в .env "
            "(Bot -> Reset Token в Discord Developer Portal)."
        )
        return 1
    except KeyboardInterrupt:
        log.info("Бот остановлен пользователем")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
