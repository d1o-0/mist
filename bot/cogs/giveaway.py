import asyncio
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from utils.giveaway_actions import (
    action_start,
    action_end,
    action_cancel,
    action_pause,
    action_resume,
    action_reroll,
    action_list,
    action_info,
    build_info_embed,
    build_entry_view,
    GiveawayView,
    PINK,
    GOLD,
    GREEN,
    RED,
    ORANGE,
    GREY,
)
from utils.giveaway_manager import get_giveaway
from utils.permissions import (
    can_manage_giveaways,
    can_configure_permissions,
    add_giveaway_role,
    remove_giveaway_role,
    clear_giveaway_roles,
    get_giveaway_roles,
)

PREFIX = "+"
DENIED_EMBED    = discord.Embed(description="❌  You don't have permission to manage giveaways.", color=RED)
ADMIN_ONLY_EMBED = discord.Embed(description="❌  Only server administrators can configure giveaway roles.", color=RED)


def _ok(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=GREEN)


def _err(description: str) -> discord.Embed:
    return discord.Embed(description=f"❌  {description}", color=RED)


def _info(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description, color=GOLD)


class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def on_giveaway_end(self, message_id: str) -> None:
        g = get_giveaway(message_id)
        if not g or g.ended or g.cancelled:
            return
        channel = self.bot.get_channel(int(g.channel_id))
        if not isinstance(channel, discord.TextChannel):
            return
        await action_end(message_id, channel)

    # ─── Slash commands ───────────────────────────────────────────────────────

    giveaway_group = app_commands.Group(name="giveaway", description="Giveaway management commands")

    @giveaway_group.command(name="start", description="Start a giveaway in this channel")
    @app_commands.describe(
        duration="Duration (e.g. 10s, 10m, 1h, 2d)",
        winners="Number of winners (1-20)",
        prize="What is being given away",
    )
    async def slash_start(
        self,
        interaction: discord.Interaction,
        duration: str,
        winners: app_commands.Range[int, 1, 20],
        prize: str,
    ):
        assert isinstance(interaction.channel, discord.TextChannel)
        assert isinstance(interaction.user, discord.Member)
        if not can_manage_giveaways(interaction.user, str(interaction.guild_id)):
            await interaction.response.send_message(embed=DENIED_EMBED, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        result = await action_start(
            channel=interaction.channel,
            prize=prize,
            duration_str=duration,
            winners_count=winners,
            hosted_by=f"<@{interaction.user.id}>",
            on_end=self.on_giveaway_end,
            loop=asyncio.get_event_loop(),
        )
        if not result["ok"]:
            await interaction.followup.send(embed=_err(result["error"]), ephemeral=True)
            return
        msg = result["message"]
        self.bot.add_view(GiveawayView(str(msg.id)), message_id=msg.id)
        await interaction.followup.send(
            embed=_ok(
                "🎉  Giveaway started!",
                f"[Jump to giveaway](https://discord.com/channels/{interaction.guild_id}/{interaction.channel_id}/{msg.id})",
            ),
            ephemeral=True,
        )

    @giveaway_group.command(name="end", description="End a giveaway early and pick winners")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def slash_end(self, interaction: discord.Interaction, message_id: str):
        assert isinstance(interaction.user, discord.Member)
        assert isinstance(interaction.channel, discord.TextChannel)
        if not can_manage_giveaways(interaction.user, str(interaction.guild_id)):
            await interaction.response.send_message(embed=DENIED_EMBED, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        result = await action_end(message_id, interaction.channel)
        await interaction.followup.send(
            embed=_ok("✅  Giveaway ended.") if result["ok"] else _err(result["error"]),
            ephemeral=True,
        )

    @giveaway_group.command(name="reroll", description="Reroll winners for an ended giveaway")
    @app_commands.describe(
        message_id="The message ID of the giveaway",
        count="Number of new winners to pick (optional)",
    )
    async def slash_reroll(
        self,
        interaction: discord.Interaction,
        message_id: str,
        count: Optional[int] = None,
    ):
        assert isinstance(interaction.user, discord.Member)
        assert isinstance(interaction.channel, discord.TextChannel)
        if not can_manage_giveaways(interaction.user, str(interaction.guild_id)):
            await interaction.response.send_message(embed=DENIED_EMBED, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        result = await action_reroll(message_id, interaction.channel, count)
        await interaction.followup.send(
            embed=_ok("✅  Rerolled!") if result["ok"] else _err(result["error"]),
            ephemeral=True,
        )

    @giveaway_group.command(name="list", description="List all active giveaways in this server")
    async def slash_list(self, interaction: discord.Interaction):
        active = action_list(str(interaction.guild_id))
        if not active:
            await interaction.response.send_message(
                embed=_info("📋  Active Giveaways", "There are no active giveaways in this server."),
                ephemeral=True,
            )
            return
        lines = [
            f"**{i+1}. {g.prize}**\n"
            f"🏆 {g.winners_count} winner{'s' if g.winners_count != 1 else ''}  "
            f"│  🎟️ {len(g.entries)} {'entries' if len(g.entries) != 1 else 'entry'}  "
            f"│  ⏰ ends <t:{int(g.ends_at.timestamp())}:R>"
            f"{'  │  ⏸️ Paused' if g.paused else ''}\n"
            f"`{g.message_id}`"
            for i, g in enumerate(active)
        ]
        embed = discord.Embed(
            title=f"📋  Active Giveaways ({len(active)})",
            description="\n\n".join(lines),
            color=GOLD,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @giveaway_group.command(name="cancel", description="Cancel a giveaway without picking winners")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def slash_cancel(self, interaction: discord.Interaction, message_id: str):
        assert isinstance(interaction.user, discord.Member)
        assert isinstance(interaction.channel, discord.TextChannel)
        if not can_manage_giveaways(interaction.user, str(interaction.guild_id)):
            await interaction.response.send_message(embed=DENIED_EMBED, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        result = await action_cancel(message_id, interaction.channel)
        await interaction.followup.send(
            embed=_ok("🚫  Giveaway cancelled.") if result["ok"] else _err(result["error"]),
            ephemeral=True,
        )

    @giveaway_group.command(name="info", description="Show details about a giveaway")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def slash_info(self, interaction: discord.Interaction, message_id: str):
        g = action_info(message_id)
        if not g:
            await interaction.response.send_message(
                embed=_err("No giveaway found with that message ID."), ephemeral=True
            )
            return
        await interaction.response.send_message(embed=build_info_embed(g), ephemeral=True)

    @giveaway_group.command(name="pause", description="Pause a running giveaway's countdown")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def slash_pause(self, interaction: discord.Interaction, message_id: str):
        assert isinstance(interaction.user, discord.Member)
        assert isinstance(interaction.channel, discord.TextChannel)
        if not can_manage_giveaways(interaction.user, str(interaction.guild_id)):
            await interaction.response.send_message(embed=DENIED_EMBED, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        result = await action_pause(message_id, interaction.channel)
        await interaction.followup.send(
            embed=_ok("⏸️  Giveaway paused.") if result["ok"] else _err(result["error"]),
            ephemeral=True,
        )

    @giveaway_group.command(name="resume", description="Resume a paused giveaway")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def slash_resume(self, interaction: discord.Interaction, message_id: str):
        assert isinstance(interaction.user, discord.Member)
        assert isinstance(interaction.channel, discord.TextChannel)
        if not can_manage_giveaways(interaction.user, str(interaction.guild_id)):
            await interaction.response.send_message(embed=DENIED_EMBED, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        result = await action_resume(
            message_id, interaction.channel, self.on_giveaway_end, asyncio.get_event_loop()
        )
        await interaction.followup.send(
            embed=_ok("▶️  Giveaway resumed.") if result["ok"] else _err(result["error"]),
            ephemeral=True,
        )

    @giveaway_group.command(name="setrole", description="(Admin) Add a role that can manage giveaways")
    @app_commands.describe(role="The role to grant giveaway management access")
    async def slash_setrole(self, interaction: discord.Interaction, role: discord.Role):
        assert isinstance(interaction.user, discord.Member)
        if not can_configure_permissions(interaction.user):
            await interaction.response.send_message(embed=ADMIN_ONLY_EMBED, ephemeral=True)
            return
        add_giveaway_role(str(interaction.guild_id), str(role.id))
        await interaction.response.send_message(
            embed=_ok("✅  Role added.", f"{role.mention} can now manage giveaways."),
            ephemeral=True,
        )

    @giveaway_group.command(name="removerole", description="(Admin) Remove a role from giveaway access")
    @app_commands.describe(role="The role to remove")
    async def slash_removerole(self, interaction: discord.Interaction, role: discord.Role):
        assert isinstance(interaction.user, discord.Member)
        if not can_configure_permissions(interaction.user):
            await interaction.response.send_message(embed=ADMIN_ONLY_EMBED, ephemeral=True)
            return
        removed = remove_giveaway_role(str(interaction.guild_id), str(role.id))
        if removed:
            await interaction.response.send_message(
                embed=_ok("✅  Role removed.", f"{role.mention} removed from giveaway access."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=_err("That role wasn't in the list."), ephemeral=True
            )

    @giveaway_group.command(name="clearroles", description="(Admin) Remove all configured giveaway roles")
    async def slash_clearroles(self, interaction: discord.Interaction):
        assert isinstance(interaction.user, discord.Member)
        if not can_configure_permissions(interaction.user):
            await interaction.response.send_message(embed=ADMIN_ONLY_EMBED, ephemeral=True)
            return
        clear_giveaway_roles(str(interaction.guild_id))
        await interaction.response.send_message(
            embed=_ok("✅  All giveaway roles cleared.", "Only admins can now manage giveaways."),
            ephemeral=True,
        )

    @giveaway_group.command(name="roles", description="Show which roles can manage giveaways")
    async def slash_roles(self, interaction: discord.Interaction):
        role_ids = get_giveaway_roles(str(interaction.guild_id))
        if not role_ids:
            await interaction.response.send_message(
                embed=_info(
                    "🔐  Giveaway Roles",
                    "No roles configured. Only members with **Manage Server** permission can use giveaway commands.",
                ),
                ephemeral=True,
            )
        else:
            mentions = "  ".join(f"<@&{rid}>" for rid in role_ids)
            await interaction.response.send_message(
                embed=_info("🔐  Giveaway Roles", mentions),
                ephemeral=True,
            )

    # ─── Prefix commands ──────────────────────────────────────────────────────

    def help_embed(self, is_admin: bool) -> discord.Embed:
        embed = discord.Embed(
            title="🎉  Giveaway Commands",
            description="Use `+giveaway <subcommand>` or `/giveaway <subcommand>`",
            color=PINK,
        )
        embed.add_field(
            name="📋  Management",
            value=(
                "`start <duration> <winners> <prize>` — Start a giveaway\n"
                "`end <id>` — End early & pick winners\n"
                "`cancel <id>` — Cancel without picking\n"
                "`pause <id>` — Freeze the countdown\n"
                "`resume <id>` — Resume a paused giveaway\n"
                "`reroll <id> [count]` — Reroll winners\n"
                "`list` — List active giveaways\n"
                "`info <id>` — Show giveaway details"
            ),
            inline=False,
        )
        if is_admin:
            embed.add_field(
                name="🔐  Admin",
                value=(
                    "`setrole @Role` — Grant role giveaway access\n"
                    "`removerole @Role` — Revoke role access\n"
                    "`clearroles` — Remove all configured roles\n"
                    "`roles` — Show configured roles"
                ),
                inline=False,
            )
        embed.set_footer(text="Duration examples: 10s • 30m • 2h • 1d")
        return embed

    @commands.group(name="giveaway", aliases=["g"], invoke_without_command=True)
    async def prefix_giveaway(self, ctx: commands.Context):
        assert isinstance(ctx.author, discord.Member)
        assert isinstance(ctx.channel, discord.TextChannel)
        assert ctx.guild

        # If the user typed extra args (e.g. +giveaway 10m 1 prize), treat as shorthand for start
        remaining = ctx.message.content.strip()
        # strip the prefix
        remaining = remaining[len(ctx.prefix or PREFIX):]
        # strip the invoked command name / alias
        parts = remaining.split(None, 1)
        remaining = parts[1].strip() if len(parts) > 1 else ""

        if remaining:
            args = remaining.split(None, 2)
            if len(args) < 3:
                await ctx.send(embed=_err("Usage: `+giveaway <duration> <winners> <prize>`\nExample: `+giveaway 10m 1 Discord Nitro`"))
                return
            duration, winners_str, prize = args[0], args[1], args[2]
            if not can_manage_giveaways(ctx.author, str(ctx.guild.id)):
                await ctx.send(embed=DENIED_EMBED)
                return
            try:
                winners_count = int(winners_str)
                if winners_count < 1 or winners_count > 20:
                    raise ValueError
            except ValueError:
                await ctx.send(embed=_err("Winners must be a number between 1 and 20."))
                return
            result = await action_start(
                channel=ctx.channel,
                prize=prize,
                duration_str=duration,
                winners_count=winners_count,
                hosted_by=f"<@{ctx.author.id}>",
                on_end=self.on_giveaway_end,
                loop=asyncio.get_event_loop(),
            )
            if not result["ok"]:
                await ctx.send(embed=_err(result["error"]))
                return
            msg = result["message"]
            self.bot.add_view(GiveawayView(str(msg.id)), message_id=msg.id)
            return

        is_admin = can_configure_permissions(ctx.author)
        await ctx.send(embed=self.help_embed(is_admin))

    @prefix_giveaway.command(name="start")
    async def prefix_start(self, ctx: commands.Context, duration: str, winners_str: str, *, prize: str):
        assert isinstance(ctx.author, discord.Member)
        assert isinstance(ctx.channel, discord.TextChannel)
        assert ctx.guild

        if not can_manage_giveaways(ctx.author, str(ctx.guild.id)):
            await ctx.send(embed=DENIED_EMBED)
            return

        try:
            winners_count = int(winners_str)
            if winners_count < 1 or winners_count > 20:
                raise ValueError
        except ValueError:
            await ctx.send(embed=_err("Winners must be a number between 1 and 20."))
            return

        result = await action_start(
            channel=ctx.channel,
            prize=prize,
            duration_str=duration,
            winners_count=winners_count,
            hosted_by=f"<@{ctx.author.id}>",
            on_end=self.on_giveaway_end,
            loop=asyncio.get_event_loop(),
        )
        if not result["ok"]:
            await ctx.send(embed=_err(result["error"]))
            return
        msg = result["message"]
        self.bot.add_view(GiveawayView(str(msg.id)), message_id=msg.id)

    @prefix_giveaway.command(name="end")
    async def prefix_end(self, ctx: commands.Context, message_id: str):
        assert isinstance(ctx.author, discord.Member)
        assert isinstance(ctx.channel, discord.TextChannel)
        assert ctx.guild
        if not can_manage_giveaways(ctx.author, str(ctx.guild.id)):
            await ctx.send(embed=DENIED_EMBED)
            return
        result = await action_end(message_id, ctx.channel)
        if not result["ok"]:
            await ctx.send(embed=_err(result["error"]))

    @prefix_giveaway.command(name="reroll")
    async def prefix_reroll(self, ctx: commands.Context, message_id: str, count: Optional[int] = None):
        assert isinstance(ctx.author, discord.Member)
        assert isinstance(ctx.channel, discord.TextChannel)
        assert ctx.guild
        if not can_manage_giveaways(ctx.author, str(ctx.guild.id)):
            await ctx.send(embed=DENIED_EMBED)
            return
        result = await action_reroll(message_id, ctx.channel, count)
        if not result["ok"]:
            await ctx.send(embed=_err(result["error"]))

    @prefix_giveaway.command(name="list")
    async def prefix_list(self, ctx: commands.Context):
        assert ctx.guild
        active = action_list(str(ctx.guild.id))
        if not active:
            await ctx.send(embed=_info("📋  Active Giveaways", "There are no active giveaways in this server."))
            return
        lines = [
            f"**{i+1}. {g.prize}**\n"
            f"🏆 {g.winners_count} winner{'s' if g.winners_count != 1 else ''}  "
            f"│  🎟️ {len(g.entries)} {'entries' if len(g.entries) != 1 else 'entry'}  "
            f"│  ⏰ ends <t:{int(g.ends_at.timestamp())}:R>"
            f"{'  │  ⏸️ Paused' if g.paused else ''}\n"
            f"`{g.message_id}`"
            for i, g in enumerate(active)
        ]
        embed = discord.Embed(
            title=f"📋  Active Giveaways ({len(active)})",
            description="\n\n".join(lines),
            color=GOLD,
        )
        await ctx.send(embed=embed)

    @prefix_giveaway.command(name="cancel")
    async def prefix_cancel(self, ctx: commands.Context, message_id: str):
        assert isinstance(ctx.author, discord.Member)
        assert isinstance(ctx.channel, discord.TextChannel)
        assert ctx.guild
        if not can_manage_giveaways(ctx.author, str(ctx.guild.id)):
            await ctx.send(embed=DENIED_EMBED)
            return
        result = await action_cancel(message_id, ctx.channel)
        if not result["ok"]:
            await ctx.send(embed=_err(result["error"]))

    @prefix_giveaway.command(name="info")
    async def prefix_info(self, ctx: commands.Context, message_id: str):
        g = action_info(message_id)
        if not g:
            await ctx.send(embed=_err("No giveaway found with that message ID."))
            return
        await ctx.send(embed=build_info_embed(g))

    @prefix_giveaway.command(name="pause")
    async def prefix_pause(self, ctx: commands.Context, message_id: str):
        assert isinstance(ctx.author, discord.Member)
        assert isinstance(ctx.channel, discord.TextChannel)
        assert ctx.guild
        if not can_manage_giveaways(ctx.author, str(ctx.guild.id)):
            await ctx.send(embed=DENIED_EMBED)
            return
        result = await action_pause(message_id, ctx.channel)
        if not result["ok"]:
            await ctx.send(embed=_err(result["error"]))
        else:
            await ctx.send(embed=_ok("⏸️  Giveaway paused."))

    @prefix_giveaway.command(name="resume")
    async def prefix_resume(self, ctx: commands.Context, message_id: str):
        assert isinstance(ctx.author, discord.Member)
        assert isinstance(ctx.channel, discord.TextChannel)
        assert ctx.guild
        if not can_manage_giveaways(ctx.author, str(ctx.guild.id)):
            await ctx.send(embed=DENIED_EMBED)
            return
        result = await action_resume(
            message_id, ctx.channel, self.on_giveaway_end, asyncio.get_event_loop()
        )
        if not result["ok"]:
            await ctx.send(embed=_err(result["error"]))
        else:
            await ctx.send(embed=_ok("▶️  Giveaway resumed."))

    @prefix_giveaway.command(name="roles")
    async def prefix_roles(self, ctx: commands.Context):
        assert ctx.guild
        role_ids = get_giveaway_roles(str(ctx.guild.id))
        if not role_ids:
            await ctx.send(
                embed=_info(
                    "🔐  Giveaway Roles",
                    "No roles configured. Only members with **Manage Server** permission can use giveaway commands.",
                )
            )
        else:
            mentions = "  ".join(f"<@&{rid}>" for rid in role_ids)
            await ctx.send(embed=_info("🔐  Giveaway Roles", mentions))

    @prefix_giveaway.command(name="setrole")
    async def prefix_setrole(self, ctx: commands.Context, role: discord.Role):
        assert isinstance(ctx.author, discord.Member)
        assert ctx.guild
        if not can_configure_permissions(ctx.author):
            await ctx.send(embed=ADMIN_ONLY_EMBED)
            return
        add_giveaway_role(str(ctx.guild.id), str(role.id))
        await ctx.send(embed=_ok("✅  Role added.", f"{role.mention} can now manage giveaways."))

    @prefix_giveaway.command(name="removerole")
    async def prefix_removerole(self, ctx: commands.Context, role: discord.Role):
        assert isinstance(ctx.author, discord.Member)
        assert ctx.guild
        if not can_configure_permissions(ctx.author):
            await ctx.send(embed=ADMIN_ONLY_EMBED)
            return
        removed = remove_giveaway_role(str(ctx.guild.id), str(role.id))
        if removed:
            await ctx.send(embed=_ok("✅  Role removed.", f"{role.mention} removed from giveaway access."))
        else:
            await ctx.send(embed=_err("That role wasn't in the list."))

    @prefix_giveaway.command(name="clearroles")
    async def prefix_clearroles(self, ctx: commands.Context):
        assert isinstance(ctx.author, discord.Member)
        assert ctx.guild
        if not can_configure_permissions(ctx.author):
            await ctx.send(embed=ADMIN_ONLY_EMBED)
            return
        clear_giveaway_roles(str(ctx.guild.id))
        await ctx.send(embed=_ok("✅  All giveaway roles cleared.", "Only admins can now manage giveaways."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
