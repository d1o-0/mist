import asyncio
import os
import sys
import logging

import discord
from discord.ext import commands

from utils.permissions import load_roles
from utils.giveaway_manager import restore_giveaways, get_all_giveaways
from utils.giveaway_actions import GiveawayView

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("bot")


class GuvBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True

        super().__init__(
            command_prefix="+",
            intents=intents,
            help_command=None,
        )
        self.launch_time = discord.utils.utcnow()

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.giveaway")
        await self.load_extension("cogs.botinfo")
        log.info("Cogs loaded.")

    async def on_ready(self) -> None:
        log.info(f"Logged in as {self.user} (ID: {self.user.id})")
        log.info(f"Connected to {len(self.guilds)} guild(s).")

        load_roles()
        log.info("Guild roles loaded from disk.")

        giveaway_cog = self.cogs.get("Giveaway")
        if giveaway_cog:
            count = restore_giveaways(
                on_end=giveaway_cog.on_giveaway_end,
                loop=asyncio.get_event_loop(),
            )
            log.info(f"Restored {count} giveaway(s) from disk.")

        for g in get_all_giveaways():
            if not g.ended and not g.cancelled:
                self.add_view(GiveawayView(g.message_id), message_id=int(g.message_id))
        log.info("Registered persistent views for active giveaways.")

        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info(f"Synced slash commands to guild: {guild.name} ({guild.id})")
            except Exception as e:
                log.error(f"Failed to sync commands to guild {guild.id}: {e}")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info(f"Joined guild: {guild.name} ({guild.id})")
        try:
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info(f"Synced slash commands to new guild: {guild.name}")
        except Exception as e:
            log.error(f"Failed to sync commands to new guild {guild.id}: {e}")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: `{error.param.name}`. Use `+giveaway help` for usage.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"Invalid argument. Use `+giveaway help` for usage.")
        elif isinstance(error, commands.CommandNotFound):
            pass
        else:
            log.error(f"Unhandled command error: {error}", exc_info=error)


async def main() -> None:
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        log.critical("DISCORD_TOKEN environment variable is not set. Exiting.")
        sys.exit(1)

    bot = GuvBot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
