"""Проверки голосового канала и получение плеера."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from music.errors import MusicError
from music.player import MusicPlayer

if TYPE_CHECKING:
    from bot import MusicBot


def human_members(channel: discord.abc.Connectable) -> list[discord.Member]:
    return [member for member in getattr(channel, "members", []) if not member.bot]


async def require_voice(member: discord.Member, bot: MusicBot) -> discord.VoiceChannel:
    """Проверяет, что пользователь в голосовом канале и бота можно туда позвать."""

    state = getattr(member, "voice", None)
    if state is None or state.channel is None:
        raise MusicError("Сначала зайдите в голосовой канал.")

    channel = state.channel
    if not isinstance(channel, discord.VoiceChannel):
        raise MusicError("Поддерживаются только обычные голосовые каналы (не Stage).")

    permissions = channel.permissions_for(member.guild.me)
    if not permissions.connect or not permissions.speak:
        raise MusicError(f"У меня нет прав подключаться или говорить в {channel.mention}.")

    player = bot.players.get(member.guild.id)
    if player is not None and player.is_connected and player.voice is not None:
        if player.voice.channel != channel and human_members(player.voice.channel):
            raise MusicError(
                "Я уже играю в другом канале. Зайдите туда или отключите меня командой `/leave`."
            )
    return channel


async def get_or_create_player(
    bot: MusicBot,
    guild: discord.Guild,
    channel: discord.VoiceChannel,
    text_channel: discord.abc.Messageable | None,
) -> MusicPlayer:
    player = bot.players.get(guild.id)
    if player is None:
        player = MusicPlayer(bot, guild, text_channel)
        bot.players[guild.id] = player
    elif text_channel is not None:
        player.text_channel = text_channel
    await player.connect(channel)
    return player
