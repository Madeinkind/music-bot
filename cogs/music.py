"""Команды управления музыкой."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import discord
from discord import app_commands
from discord.ext import commands

from music.errors import MusicError
from music.player import LoopMode, MusicPlayer
from music.voice import get_or_create_player, require_voice
from music.ytdl import is_url
from utils import embeds
from utils.formatting import format_duration

if TYPE_CHECKING:
    from bot import MusicBot

log = logging.getLogger(__name__)


async def _reply(
    ctx: commands.Context,
    embed: discord.Embed,
    *,
    ephemeral: bool = False,
    view: discord.ui.View | None = None,
) -> None:
    """Отвечает и на слэш-, и на префиксную команду."""

    if ctx.interaction is not None:
        if ctx.interaction.response.is_done():
            await ctx.interaction.followup.send(embed=embed, view=view, ephemeral=ephemeral)
        else:
            await ctx.interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
    else:
        await ctx.reply(embed=embed, view=view)


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "нет"


class Music(commands.Cog):
    """Воспроизведение музыки и управление очередью."""

    def __init__(self, bot: MusicBot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------ вспомогательное

    async def _prepare(self, ctx: commands.Context) -> MusicPlayer | None:
        """Проверяет голосовой канал и подключает бота."""

        try:
            channel = await require_voice(ctx.author, self.bot)
            return await get_or_create_player(self.bot, ctx.guild, channel, ctx.channel)
        except MusicError as exc:
            await _reply(ctx, embeds.error(str(exc)), ephemeral=True)
            return None

    def _existing(self, ctx: commands.Context) -> MusicPlayer | None:
        return self.bot.players.get(ctx.guild.id)

    # ------------------------------------------------------------------ воспроизведение

    @commands.hybrid_command(name="play", aliases=["p", "п", "играть"], description="Включить трек или плейлист")
    @app_commands.describe(query="Название трека или ссылка (YouTube, SoundCloud, Bandcamp…)")
    @commands.guild_only()
    async def play(self, ctx: commands.Context, *, query: str) -> None:
        """Ищет трек по названию или разбирает ссылку и добавляет в очередь."""

        await ctx.defer()
        player = await self._prepare(ctx)
        if player is None:
            return

        limit = self.bot.config.max_playlist_items if is_url(query) else 1
        try:
            tracks = await self.bot.ytdl.resolve(query, requester=ctx.author, limit=limit)
        except MusicError as exc:
            await _reply(ctx, embeds.error(str(exc)))
            return

        added, skipped = player.enqueue(tracks)
        await _reply(ctx, embeds.enqueue_embed(tracks, player, added=added, skipped=skipped))
        if player.current is None:
            await player.play_next()

    @commands.hybrid_command(
        name="search",
        aliases=["find", "поиск"],
        description="Найти трек и выбрать из результатов",
    )
    @app_commands.describe(query="Поисковый запрос")
    @commands.guild_only()
    async def search(self, ctx: commands.Context, *, query: str) -> None:
        """Показывает пять результатов поиска с выбором."""

        from music.views import SearchView

        await ctx.defer()
        player = await self._prepare(ctx)
        if player is None:
            return

        try:
            tracks = await self.bot.ytdl.resolve(query, requester=ctx.author, limit=5)
        except MusicError as exc:
            await _reply(ctx, embeds.error(str(exc)))
            return

        await _reply(
            ctx,
            embeds.search_embed(tracks),
            view=SearchView(self.bot, tracks, ctx.author.id),
        )

    @commands.hybrid_command(name="pause", aliases=["пауза"], description="Поставить воспроизведение на паузу")
    @commands.guild_only()
    async def pause(self, ctx: commands.Context) -> None:
        player = self._existing(ctx)
        if player is None or player.voice is None or player.current is None:
            await _reply(ctx, embeds.error("Сейчас ничего не играет."), ephemeral=True)
            return
        if player.voice.is_paused():
            await _reply(ctx, embeds.info("Уже на паузе."))
            return
        if player.pause():
            await _reply(ctx, embeds.success("Пауза. Продолжить — `/resume`."))
        else:
            await _reply(ctx, embeds.error("Сейчас ничего не играет."), ephemeral=True)

    @commands.hybrid_command(
        name="resume",
        aliases=["continue", "продолжить"],
        description="Продолжить воспроизведение",
    )
    @commands.guild_only()
    async def resume(self, ctx: commands.Context) -> None:
        player = self._existing(ctx)
        if player is None or player.voice is None or player.current is None:
            await _reply(ctx, embeds.error("Сейчас ничего не играет."), ephemeral=True)
            return
        if player.resume():
            await _reply(ctx, embeds.success("Продолжаю."))
        else:
            await _reply(ctx, embeds.info("Воспроизведение и так идёт."))

    @commands.hybrid_command(name="skip", aliases=["next", "пропустить", "след"], description="Пропустить текущий трек")
    @commands.guild_only()
    async def skip(self, ctx: commands.Context) -> None:
        player = self._existing(ctx)
        if player is None or not await player.skip():
            await _reply(ctx, embeds.info("Пропускать нечего — очередь пуста."), ephemeral=True)
            return
        await _reply(ctx, embeds.success("Трек пропущен."))

    @commands.hybrid_command(name="stop", aliases=["стоп"], description="Остановить воспроизведение и очистить очередь")
    @commands.guild_only()
    async def stop(self, ctx: commands.Context) -> None:
        player = self._existing(ctx)
        if player is None:
            await _reply(ctx, embeds.info("Сейчас ничего не играет."), ephemeral=True)
            return
        await player.stop()
        await _reply(ctx, embeds.success("Воспроизведение остановлено, очередь очищена."))

    @commands.hybrid_command(name="seek", aliases=["перемотка"], description="Перемотать текущий трек")
    @app_commands.describe(seconds="Позиция в секундах от начала трека")
    @commands.guild_only()
    async def seek(self, ctx: commands.Context, seconds: int) -> None:
        player = self._existing(ctx)
        if player is None or player.current is None:
            await _reply(ctx, embeds.error("Сейчас ничего не играет."), ephemeral=True)
            return
        await ctx.defer()
        try:
            await player.seek(seconds)
        except MusicError as exc:
            await _reply(ctx, embeds.error(str(exc)))
            return
        await _reply(ctx, embeds.success(f"Перемотал на {format_duration(seconds)}."))

    # ------------------------------------------------------------------ очередь

    @commands.hybrid_command(name="queue", aliases=["q", "очередь"], description="Показать очередь")
    @commands.guild_only()
    async def queue(self, ctx: commands.Context) -> None:
        from music.views import QueueView

        player = self._existing(ctx)
        if player is None or (player.current is None and not player.queue):
            await _reply(ctx, embeds.info("Очередь пуста. Добавьте треки командой `/play`."), ephemeral=True)
            return
        embed, pages = embeds.queue_embed(player)
        await _reply(ctx, embed, view=QueueView(player) if pages > 1 else None)

    @commands.hybrid_command(name="nowplaying", aliases=["np", "current", "сейчас"], description="Что сейчас играет")
    @commands.guild_only()
    async def nowplaying(self, ctx: commands.Context) -> None:
        from music.views import NowPlayingView

        player = self._existing(ctx)
        if player is None or player.current is None:
            await _reply(ctx, embeds.info("Сейчас ничего не играет."), ephemeral=True)
            return
        await _reply(
            ctx,
            embeds.now_playing_embed(player.current, player),
            view=NowPlayingView(player),
        )

    @commands.hybrid_command(name="remove", aliases=["rm", "удалить"], description="Удалить трек из очереди")
    @app_commands.describe(index="Номер трека в очереди (см. /queue)")
    @commands.guild_only()
    async def remove(self, ctx: commands.Context, index: int) -> None:
        player = self._existing(ctx)
        if player is None or not player.queue:
            await _reply(ctx, embeds.error("Очередь пуста."), ephemeral=True)
            return
        if not 1 <= index <= len(player.queue):
            await _reply(
                ctx,
                embeds.error(f"В очереди {len(player.queue)} трек(ов), номер должен быть от 1 до {len(player.queue)}."),
                ephemeral=True,
            )
            return
        track = player.queue.remove(index - 1)
        await _reply(ctx, embeds.success(f"Удалён из очереди: **{track.title}**"))

    @commands.hybrid_command(name="clear", aliases=["очистить"], description="Очистить очередь")
    @commands.guild_only()
    async def clear(self, ctx: commands.Context) -> None:
        player = self._existing(ctx)
        if player is None or not player.queue:
            await _reply(ctx, embeds.info("Очередь уже пуста."), ephemeral=True)
            return
        count = len(player.queue)
        player.queue.clear()
        await _reply(ctx, embeds.success(f"Очередь очищена ({count} трек(ов))."))

    @commands.hybrid_command(name="shuffle", aliases=["mix", "перемешать"], description="Перемешать очередь")
    @commands.guild_only()
    async def shuffle(self, ctx: commands.Context) -> None:
        player = self._existing(ctx)
        if player is None or len(player.queue) < 2:
            await _reply(ctx, embeds.info("В очереди слишком мало треков для перемешивания."), ephemeral=True)
            return
        player.queue.shuffle()
        await _reply(ctx, embeds.success(f"Очередь перемешана ({len(player.queue)} трек(ов))."))

    @commands.hybrid_command(name="loop", aliases=["repeat", "повтор"], description="Режим повтора")
    @app_commands.describe(mode="off — выключить, track — повторять трек, queue — повторять очередь")
    @commands.guild_only()
    async def loop(
        self,
        ctx: commands.Context,
        mode: Literal["off", "track", "queue"] | None = None,
    ) -> None:
        player = self._existing(ctx)
        if player is None:
            await _reply(ctx, embeds.info("Сейчас ничего не играет."), ephemeral=True)
            return
        if mode is None:
            player.loop_mode = player.loop_mode.next()
        else:
            player.loop_mode = LoopMode(mode)
        await _reply(ctx, embeds.success(f"Режим повтора: **{player.loop_mode.label}**."))

    # ------------------------------------------------------------------ канал и громкость

    @commands.hybrid_command(
        name="join",
        aliases=["connect", "зайти"],
        description="Подключиться к вашему голосовому каналу",
    )
    @commands.guild_only()
    async def join(self, ctx: commands.Context) -> None:
        player = await self._prepare(ctx)
        if player is None:
            return
        channel = getattr(ctx.author.voice, "channel", None)
        await _reply(ctx, embeds.success(f"Подключился к {channel.mention if channel else 'каналу'}."))

    @commands.hybrid_command(name="leave", aliases=["dc", "disconnect", "выйти"], description="Отключиться от канала")
    @commands.guild_only()
    async def leave(self, ctx: commands.Context) -> None:
        player = self._existing(ctx)
        if player is None or not player.is_connected:
            await _reply(ctx, embeds.info("Я не в голосовом канале."), ephemeral=True)
            return
        await player.disconnect()
        await _reply(ctx, embeds.success("Вышел из канала, очередь очищена."))

    @commands.hybrid_command(name="volume", aliases=["vol", "громкость"], description="Громкость воспроизведения")
    @app_commands.describe(level="Громкость от 0 до 200 (100 — обычная)")
    @commands.guild_only()
    async def volume(self, ctx: commands.Context, level: int) -> None:
        player = self._existing(ctx)
        if player is None:
            await _reply(ctx, embeds.error("Сейчас ничего не играет."), ephemeral=True)
            return
        volume = player.set_volume(level)
        await _reply(ctx, embeds.success(f"Громкость: **{volume}%**."))

    @commands.hybrid_command(
        name="voicecheck",
        aliases=["vcheck", "диагностика"],
        description="Проверить голосовое подключение и звук",
    )
    @commands.guild_only()
    async def voicecheck(self, ctx: commands.Context) -> None:
        """Показывает состояние голосового подключения и окружения."""

        if ctx.guild is None:
            return

        player = self._existing(ctx)
        lines: list[str] = []

        if player is None or not player.is_connected or player.voice is None:
            lines.append("**Подключение:** бот не в голосовом канале.")
        else:
            channel = player.voice.channel
            if player.voice.is_paused():
                playback = "пауза"
            elif player.voice.is_playing():
                playback = "идёт"
            else:
                playback = "нет"
            lines.append(f"**Канал:** {channel.mention if channel else '?'}")
            lines.append(f"**Воспроизведение:** {playback}")
            lines.append(f"**Громкость бота:** {player.volume}%")

            me = ctx.guild.me
            if me is not None and channel is not None:
                perms = channel.permissions_for(me)
                lines.append(
                    "**Права бота:** подключаться — "
                    f"{'да' if perms.connect else 'НЕТ'}, говорить — {'да' if perms.speak else 'НЕТ'}"
                )
                state = me.voice
                if state is not None:
                    lines.append(
                        "**Состояние:** "
                        f"заглушён сервером — {'да' if state.mute else 'нет'}, "
                        f"оглушён сервером — {'да' if state.deaf else 'нет'}, "
                        f"самоглушение — {'да' if state.self_deaf else 'нет'}"
                    )
            lines.append(f"**Задержка голоса:** {player.voice.average_latency:.0f} мс")

        lines.append(f"**Opus:** {'загружен' if discord.opus.is_loaded() else 'ещё не загружался'}")
        lines.append(f"**ffmpeg:** `{Path(self.bot.ffmpeg_path).name}`")
        lines.append(f"**PyNaCl:** {_package_version('PyNaCl')} | **davey:** {_package_version('davey')}")
        lines.append("")
        lines.append(
            "Если всё в порядке, но звука нет: правый клик по боту → «Громкость пользователя» "
            "и проверьте, что вы сами не в режиме «Отключить звук»."
        )
        await _reply(ctx, embeds.info("\n".join(lines), title="Диагностика голоса"), ephemeral=True)

    @commands.hybrid_command(name="help", aliases=["помощь", "commands"], description="Список команд")
    async def help(self, ctx: commands.Context) -> None:
        await _reply(ctx, embeds.help_embed(self.bot.config.prefix), ephemeral=True)

    # ------------------------------------------------------------------ ошибки слэш-команд

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, MusicError):
            text = str(original)
        elif isinstance(original, app_commands.MissingPermissions):
            text = "У меня не хватает прав для этой команды."
        elif isinstance(original, app_commands.BotMissingPermissions):
            text = "Боту не хватает прав: " + ", ".join(original.missing_permissions)
        elif isinstance(original, app_commands.CommandOnCooldown):
            text = f"Слишком часто. Подождите {original.retry_after:.0f} с."
        else:
            log.error("Ошибка слэш-команды", exc_info=original)
            text = "Произошла непредвиденная ошибка. Подробности в логах бота."

        embed = embeds.error(text)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: MusicBot) -> None:
    await bot.add_cog(Music(bot))
