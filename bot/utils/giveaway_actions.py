import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable

import discord

log = logging.getLogger("giveaway")

from utils.giveaway_manager import (
    Giveaway,
    create_giveaway,
    get_giveaway,
    get_active_by_guild,
    mark_ended,
    cancel_giveaway,
    pause_giveaway,
    resume_giveaway,
    pick_winners,
    parse_duration,
    format_duration,
    update_message_id,
)

ENTER_BUTTON_ID = "giveaway_enter:"
LEAVE_BUTTON_ID = "giveaway_leave:"

PINK   = 0xF47FFF
GOLD   = 0xFFD700
GREEN  = 0x57F287
RED    = 0xED4245
ORANGE = 0xFF8C00
GREY   = 0x95A5A6


def _err_embed(description: str) -> discord.Embed:
    return discord.Embed(description=f"❌  {description}", color=RED)


def build_active_embed(g: Giveaway) -> discord.Embed:
    if g.paused:
        footer = "⏸️  Giveaway paused"
        color  = ORANGE
        ts_line = "⏸️ **Paused** — timer frozen"
    else:
        ts     = int(g.ends_at.timestamp())
        ts_line = f"⏰  Ends <t:{ts}:R>  •  <t:{ts}:t>"
        footer = "Click Enter to join!"
        color  = PINK

    embed = discord.Embed(
        title=f"🎁  {g.prize}",
        description=(
            f"{ts_line}\n\n"
            f">>> 🏆  **{g.winners_count}** winner{'s' if g.winners_count != 1 else ''}  "
            f"│  🎟️  **{len(g.entries)}** {'entries' if len(g.entries) != 1 else 'entry'}  "
            f"│  👤  {g.hosted_by}"
        ),
        color=color,
    )
    embed.set_footer(text=footer)
    return embed


def build_ended_embed(g: Giveaway, winners: list[str]) -> discord.Embed:
    if winners:
        winners_text = "  ".join(f"<@{uid}>" for uid in winners)
        desc = f"**🏆  Winner{'s' if len(winners) != 1 else ''}:**\n{winners_text}"
    else:
        desc = "*No valid entries — no winners picked.*"

    embed = discord.Embed(
        title=f"🎊  Giveaway Ended — {g.prize}",
        description=desc,
        color=GREEN,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Total entries", value=str(len(g.entries)), inline=True)
    embed.add_field(name="Hosted by", value=g.hosted_by, inline=True)
    embed.set_footer(text="Giveaway ended")
    return embed


def build_cancelled_embed(g: Giveaway) -> discord.Embed:
    embed = discord.Embed(
        title="🚫  Giveaway Cancelled",
        description=f"**{g.prize}** has been cancelled.",
        color=RED,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Hosted by", value=g.hosted_by, inline=True)
    return embed


def build_info_embed(g: Giveaway) -> discord.Embed:
    if g.ended:
        status = "⛔  Ended"
        color  = GREY
    elif g.cancelled:
        status = "🚫  Cancelled"
        color  = GREY
    elif g.paused:
        status = "⏸️  Paused"
        color  = ORANGE
    else:
        status = "🟢  Active"
        color  = PINK

    ts = int(g.ends_at.timestamp())
    ends_str = "—" if (g.ended or g.cancelled) else f"<t:{ts}:F>"

    lines = [
        f"**Prize:** {g.prize}",
        f"**Status:** {status}",
        f"**Entries:** {len(g.entries)}",
        f"**Winners:** {g.winners_count}",
        f"**Hosted by:** {g.hosted_by}",
        f"**Ends:** {ends_str}",
        f"**Message ID:** `{g.message_id}`",
    ]
    if g.paused and g.remaining_ms is not None:
        lines.append(f"**Time remaining:** {format_duration(g.remaining_ms)} *(paused)*")

    embed = discord.Embed(
        title="📋  Giveaway Info",
        description="\n".join(lines),
        color=color,
    )
    return embed


def build_entry_view(message_id: str) -> "GiveawayView":
    return GiveawayView(message_id)


class GiveawayView(discord.ui.View):
    def __init__(self, message_id: str):
        super().__init__(timeout=None)
        self.giveaway_message_id = message_id

        enter_btn = discord.ui.Button(
            label="Enter Giveaway",
            emoji="🎉",
            style=discord.ButtonStyle.primary,
            custom_id=f"{ENTER_BUTTON_ID}{message_id}",
        )
        leave_btn = discord.ui.Button(
            label="Leave",
            emoji="🚪",
            style=discord.ButtonStyle.secondary,
            custom_id=f"{LEAVE_BUTTON_ID}{message_id}",
        )
        enter_btn.callback = self._enter
        leave_btn.callback = self._leave
        self.add_item(enter_btn)
        self.add_item(leave_btn)

    async def _enter(self, interaction: discord.Interaction) -> None:
        from utils.giveaway_manager import add_entry
        g = get_giveaway(self.giveaway_message_id)
        log.info(f"[ENTER] id={self.giveaway_message_id!r} found={g is not None} ended={getattr(g,'ended',None)} cancelled={getattr(g,'cancelled',None)}")
        if not g or g.ended or g.cancelled:
            await interaction.response.send_message(
                embed=_err_embed("This giveaway has already ended." if (g and (g.ended or g.cancelled)) else "Giveaway not found — it may have been cancelled."),
                ephemeral=True,
            )
            return
        if g.paused:
            await interaction.response.send_message(
                embed=_err_embed("This giveaway is currently paused."), ephemeral=True
            )
            return
        joined = add_entry(self.giveaway_message_id, str(interaction.user.id))
        if joined:
            await interaction.response.edit_message(embed=build_active_embed(g), view=self)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"✅  You've entered **{g.prize}**! Good luck 🍀",
                    color=GREEN,
                ),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="You're already entered in this giveaway.",
                    color=GREY,
                ),
                ephemeral=True,
            )

    async def _leave(self, interaction: discord.Interaction) -> None:
        from utils.giveaway_manager import remove_entry
        g = get_giveaway(self.giveaway_message_id)
        if not g or g.ended or g.cancelled:
            await interaction.response.send_message(
                embed=_err_embed("This giveaway is no longer active."), ephemeral=True
            )
            return
        left = remove_entry(self.giveaway_message_id, str(interaction.user.id))
        if left:
            await interaction.response.edit_message(embed=build_active_embed(g), view=self)
            await interaction.followup.send(
                embed=discord.Embed(description="You've left the giveaway.", color=GREY),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="You weren't entered in this giveaway.",
                    color=GREY,
                ),
                ephemeral=True,
            )


async def action_start(
    channel: discord.TextChannel,
    prize: str,
    duration_str: str,
    winners_count: int,
    hosted_by: str,
    on_end: Callable[[str], Awaitable[None]],
    loop: asyncio.AbstractEventLoop,
) -> dict:
    duration_ms = parse_duration(duration_str)
    if not duration_ms or duration_ms < 10_000:
        return {"ok": False, "error": "Invalid duration. Use formats like `10s`, `10m`, `1h`, `2d`. Minimum is 10 seconds."}

    ends_at = datetime.utcnow() + timedelta(milliseconds=duration_ms)

    g = create_giveaway(
        message_id="pending",
        channel_id=str(channel.id),
        guild_id=str(channel.guild.id),
        prize=prize,
        winners_count=winners_count,
        ends_at=ends_at,
        hosted_by=hosted_by,
    )

    embed = build_active_embed(g)
    msg = await channel.send(embed=embed)

    update_message_id("pending", str(msg.id))
    view = build_entry_view(g.message_id)
    await msg.edit(embed=build_active_embed(g), view=view)

    async def _wait_and_end():
        await asyncio.sleep(duration_ms / 1000)
        await on_end(g.message_id)

    g.task = loop.create_task(_wait_and_end())

    return {"ok": True, "message": msg, "giveaway": g}


async def action_end(
    message_id: str,
    channel: discord.TextChannel,
) -> dict:
    g = get_giveaway(message_id)
    if not g:
        return {"ok": False, "error": "No giveaway found with that message ID."}
    if g.ended:
        return {"ok": False, "error": "That giveaway has already ended."}
    if g.cancelled:
        return {"ok": False, "error": "That giveaway was cancelled."}

    mark_ended(message_id)
    winners = pick_winners(message_id)

    try:
        msg = await channel.fetch_message(int(message_id))
        await msg.edit(embed=build_ended_embed(g, winners), view=None)
    except Exception:
        pass

    if winners:
        mentions = "  ".join(f"<@{uid}>" for uid in winners)
        announcement = discord.Embed(
            title="🎉  Congratulations!",
            description=f"{mentions}\nyou won **{g.prize}**!",
            color=GOLD,
        )
        announcement.set_footer(text=f"Hosted by {g.hosted_by.replace('<@', '').replace('>', '')}")
        await channel.send(embed=announcement)
    else:
        await channel.send(
            embed=discord.Embed(
                description=f"No valid entries for **{g.prize}**. Giveaway ended with no winners.",
                color=GREY,
            )
        )

    return {"ok": True, "winners": winners}


async def action_cancel(
    message_id: str,
    channel: discord.TextChannel,
) -> dict:
    g = get_giveaway(message_id)
    if not g:
        return {"ok": False, "error": "No giveaway found with that message ID."}
    if g.ended:
        return {"ok": False, "error": "That giveaway has already ended."}
    if g.cancelled:
        return {"ok": False, "error": "That giveaway is already cancelled."}

    cancel_giveaway(message_id)

    try:
        msg = await channel.fetch_message(int(message_id))
        await msg.edit(embed=build_cancelled_embed(g), view=None)
    except Exception:
        pass

    return {"ok": True}


async def action_pause(
    message_id: str,
    channel: discord.TextChannel,
) -> dict:
    g = get_giveaway(message_id)
    if not g:
        return {"ok": False, "error": "No giveaway found with that message ID."}
    if g.ended or g.cancelled:
        return {"ok": False, "error": "That giveaway is no longer active."}
    if g.paused:
        return {"ok": False, "error": "That giveaway is already paused."}

    pause_giveaway(message_id)

    try:
        msg = await channel.fetch_message(int(message_id))
        await msg.edit(embed=build_active_embed(g))
    except Exception:
        pass

    return {"ok": True}


async def action_resume(
    message_id: str,
    channel: discord.TextChannel,
    on_end: Callable[[str], Awaitable[None]],
    loop: asyncio.AbstractEventLoop,
) -> dict:
    g = get_giveaway(message_id)
    if not g:
        return {"ok": False, "error": "No giveaway found with that message ID."}
    if not g.paused:
        return {"ok": False, "error": "That giveaway is not paused."}

    resume_giveaway(message_id, on_end, loop)

    try:
        msg = await channel.fetch_message(int(message_id))
        await msg.edit(embed=build_active_embed(g), view=build_entry_view(message_id))
    except Exception:
        pass

    return {"ok": True}


async def action_reroll(
    message_id: str,
    channel: discord.TextChannel,
    count: Optional[int] = None,
) -> dict:
    g = get_giveaway(message_id)
    if not g:
        return {"ok": False, "error": "No giveaway found with that message ID."}
    if not g.ended:
        return {"ok": False, "error": "That giveaway is still running. End it first."}

    winners = pick_winners(message_id, count)
    if not winners:
        return {"ok": False, "error": "No entries to reroll from."}

    mentions = "  ".join(f"<@{uid}>" for uid in winners)
    embed = discord.Embed(
        title="🔄  Reroll!",
        description=f"New winner{'s' if len(winners) != 1 else ''} for **{g.prize}**:\n{mentions} 🎉",
        color=GOLD,
    )
    await channel.send(embed=embed)
    return {"ok": True, "winners": winners}


def action_list(guild_id: str) -> list[Giveaway]:
    return get_active_by_guild(guild_id)


def action_info(message_id: str) -> Optional[Giveaway]:
    return get_giveaway(message_id)
