"""Слушатели событий: запуск, отключение от голоса и ошибки префиксных команд."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from music.errors import MusicError
from utils import embeds

if TYPE_CHECKING:
    from bot import MusicBot

log = logging.getLogger(__name__)


class Events(commands.Cog):
    def __init__(self, bot: MusicBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self.bot.user is None:
            return
        log.info(
            "Бот запущен: %s (id=%s), серверов: %d, пользователей: %d",
            self.bot.user,
            self.bot.user.id,
            len(self.bot.guilds),
            sum(guild.member_count or 0 for guild in self.bot.guilds),
        )
        await self.bot.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"{self.bot.config.prefix}play • /play",
            ),
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if self.bot.user is None or member.id != self.bot.user.id:
            return
        if after.channel is not None:
            return
        # Бота отключили или выгнали из канала — сбрасываем состояние плеера.
        player = self.bot.players.get(member.guild.id)
        if player is not None:
            log.info("Бот отключён от канала на сервере %s, сбрасываю плеер", member.guild.id)
            player.cleanup()

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return

        original = getattr(error, "original", error)

        if isinstance(original, MusicError):
            await ctx.reply(embed=embeds.error(str(original)))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                embed=embeds.error(
                    f"Не хватает аргумента `{error.param.name}`. "
                    f"Смотрите `{self.bot.config.prefix}help`."
                )
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.reply(embed=embeds.error("Неверный аргумент. Проверьте значение и попробуйте снова."))
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.reply(embed=embeds.error("Команда работает только на сервере."))
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(embed=embeds.error(f"Слишком часто. Подождите {error.retry_after:.0f} с."))
        elif isinstance(error, commands.CheckFailure):
            await ctx.reply(embed=embeds.error("У вас нет прав на эту команду."))
        else:
            log.error("Необработанная ошибка команды %s", ctx.command, exc_info=original)
            await ctx.reply(embed=embeds.error("Произошла непредвиденная ошибка. Подробности в логах бота."))


async def setup(bot: MusicBot) -> None:
    await bot.add_cog(Events(bot))
