"""Интерактивные элементы: кнопки плеера, очередь и выбор трека."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

from music.errors import MusicError
from utils import embeds
from utils.formatting import truncate

if TYPE_CHECKING:
    from bot import MusicBot
    from music.player import MusicPlayer

log = logging.getLogger(__name__)


async def _respond(interaction: discord.Interaction, embed: discord.Embed) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def _ensure_same_voice(interaction: discord.Interaction, player: MusicPlayer) -> bool:
    member = interaction.user
    state = getattr(member, "voice", None)
    if state is None or state.channel is None:
        await _respond(interaction, embeds.error("Зайдите в тот же голосовой канал, что и бот."))
        return False
    if player.voice is not None and player.voice.channel is not None and state.channel != player.voice.channel:
        await _respond(interaction, embeds.error("Вы должны быть в том же голосовом канале, что и бот."))
        return False
    return True


class NowPlayingView(discord.ui.View):
    """Кнопки управления под сообщением «Сейчас играет»."""

    def __init__(self, player: MusicPlayer) -> None:
        super().__init__(timeout=900)
        self.player = player

        self.pause_button = discord.ui.Button(emoji="⏸️", label="Пауза", style=discord.ButtonStyle.secondary)
        self.pause_button.callback = self._toggle_pause
        self.skip_button = discord.ui.Button(emoji="⏭️", label="Пропустить", style=discord.ButtonStyle.primary)
        self.skip_button.callback = self._skip
        self.stop_button = discord.ui.Button(emoji="⏹️", label="Стоп", style=discord.ButtonStyle.danger)
        self.stop_button.callback = self._stop
        self.loop_button = discord.ui.Button(emoji="🔁", label="Повтор", style=discord.ButtonStyle.secondary)
        self.loop_button.callback = self._cycle_loop
        self.queue_button = discord.ui.Button(emoji="📜", label="Очередь", style=discord.ButtonStyle.secondary)
        self.queue_button.callback = self._show_queue

        for button in (
            self.pause_button,
            self.skip_button,
            self.stop_button,
            self.loop_button,
            self.queue_button,
        ):
            self.add_item(button)
        self._sync()

    def _sync(self) -> None:
        paused = bool(self.player.voice and self.player.voice.is_paused())
        self.pause_button.label = "Продолжить" if paused else "Пауза"
        self.pause_button.emoji = "▶️" if paused else "⏸️"
        self.loop_button.label = f"Повтор: {self.player.loop_mode.label}"
        self.loop_button.style = (
            discord.ButtonStyle.success if self.player.loop_mode.value != "off" else discord.ButtonStyle.secondary
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _ensure_same_voice(interaction, self.player)

    async def _toggle_pause(self, interaction: discord.Interaction) -> None:
        player = self.player
        if player.voice is None or player.current is None:
            await _respond(interaction, embeds.error("Сейчас ничего не играет."))
            return
        if player.voice.is_paused():
            player.resume()
        elif player.voice.is_playing():
            player.pause()
        self._sync()
        await interaction.response.edit_message(view=self)

    async def _skip(self, interaction: discord.Interaction) -> None:
        # Сразу подтверждаем нажатие: загрузка следующего трека может занять пару секунд.
        await interaction.response.defer()
        if not await self.player.skip():
            await _respond(interaction, embeds.info("Очередь пуста — пропускать нечего."))

    async def _stop(self, interaction: discord.Interaction) -> None:
        await self.player.stop()
        await interaction.response.edit_message(
            embed=embeds.info("Воспроизведение остановлено, очередь очищена."),
            view=None,
        )

    async def _cycle_loop(self, interaction: discord.Interaction) -> None:
        self.player.loop_mode = self.player.loop_mode.next()
        self._sync()
        await interaction.response.edit_message(view=self)

    async def _show_queue(self, interaction: discord.Interaction) -> None:
        embed, _ = embeds.queue_embed(self.player)
        await _respond(interaction, embed)


class QueueView(discord.ui.View):
    """Постраничный просмотр очереди."""

    def __init__(self, player: MusicPlayer) -> None:
        super().__init__(timeout=300)
        self.player = player
        self.page = 1

        self.prev_button = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary, disabled=True)
        self.prev_button.callback = self._prev
        self.next_button = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary)
        self.next_button.callback = self._next
        self.close_button = discord.ui.Button(emoji="✖️", label="Закрыть", style=discord.ButtonStyle.danger)
        self.close_button.callback = self._close
        for button in (self.prev_button, self.next_button, self.close_button):
            self.add_item(button)
        self._sync()

    def _sync(self) -> None:
        _, pages = embeds.queue_embed(self.player, self.page)
        self.prev_button.disabled = self.page <= 1
        self.next_button.disabled = self.page >= pages

    async def _prev(self, interaction: discord.Interaction) -> None:
        self.page = max(1, self.page - 1)
        self._sync()
        embed, _ = embeds.queue_embed(self.player, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _next(self, interaction: discord.Interaction) -> None:
        embed, pages = embeds.queue_embed(self.player, self.page + 1)
        self.page = min(pages, self.page + 1)
        self._sync()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=None)


class SearchView(discord.ui.View):
    """Выбор трека из результатов поиска."""

    def __init__(self, bot: MusicBot, tracks: list[Any], author_id: int) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.tracks = tracks
        self.author_id = author_id

        options = [
            discord.SelectOption(
                label=truncate(track.title, 95),
                description=truncate(track.duration_text, 95),
                value=str(index),
            )
            for index, track in enumerate(tracks[:25])
        ]
        self.select = discord.ui.Select(placeholder="Выберите трек…", options=options, min_values=1, max_values=1)
        self.select.callback = self._on_select
        self.add_item(self.select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await _respond(
                interaction,
                embeds.error("Этот поиск запустил другой пользователь. Вызовите `/search` сами."),
            )
            return False
        return True

    async def _on_select(self, interaction: discord.Interaction) -> None:
        # Импорты внутри метода — модули зависят друг от друга только в рантайме.
        from music.voice import get_or_create_player, require_voice

        await interaction.response.defer()

        index = int(interaction.data["values"][0])  # type: ignore[index]
        track = self.tracks[index]
        member = interaction.user

        try:
            if not isinstance(member, discord.Member):
                raise MusicError("Команда доступна только на сервере.")
            channel = await require_voice(member, self.bot)
            player = await get_or_create_player(self.bot, member.guild, channel, interaction.channel)
        except MusicError as exc:
            await interaction.followup.send(embed=embeds.error(str(exc)), ephemeral=True)
            return

        added, skipped = player.enqueue([track])
        await interaction.followup.send(
            embed=embeds.enqueue_embed([track], player, added=added, skipped=skipped),
            ephemeral=True,
        )
        if player.current is None:
            await player.play_next()

        self.select.disabled = True
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            log.debug("Не удалось обновить сообщение поиска", exc_info=True)
