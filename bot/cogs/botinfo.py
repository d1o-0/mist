import discord
from discord.ext import commands
from discord import app_commands


class BotInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def build_embed(self) -> discord.Embed:
        bot = self.bot
        uptime_ms = int(
            (discord.utils.utcnow() - bot.launch_time).total_seconds() * 1000
        ) if hasattr(bot, "launch_time") else 0

        parts = []
        days = uptime_ms // 86_400_000
        uptime_ms %= 86_400_000
        hours = uptime_ms // 3_600_000
        uptime_ms %= 3_600_000
        minutes = uptime_ms // 60_000
        uptime_ms %= 60_000
        seconds = uptime_ms // 1000
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        uptime_str = " ".join(parts)

        app = bot.application
        owner = app.owner if app else None
        if owner:
            owner_str = f"{owner} (<@{owner.id}>)"
        else:
            owner_str = "Unknown"

        created_at = bot.user.created_at if bot.user else None
        created_str = (
            f"<t:{int(created_at.timestamp())}:D>" if created_at else "Unknown"
        )

        embed = discord.Embed(
            title=f"{bot.user.name if bot.user else 'Bot'} Info",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow(),
        )
        if bot.user:
            embed.set_thumbnail(url=bot.user.display_avatar.url)
        embed.add_field(name="👑 Owner", value=owner_str, inline=False)
        embed.add_field(name="🎯 Purpose", value="Private giveaway management bot", inline=False)
        embed.add_field(name="🌐 Servers", value=str(len(bot.guilds)), inline=True)
        embed.add_field(name="⏱️ Uptime", value=uptime_str, inline=True)
        embed.add_field(name="📅 Bot Created", value=created_str, inline=True)
        embed.add_field(name="🤖 Library", value="discord.py v2", inline=True)
        embed.add_field(name="⚙️ Prefix", value="`+giveaway` or `/giveaway`", inline=True)
        embed.add_field(name="🔒 Access", value="Private — invite only", inline=True)
        if bot.user:
            embed.set_footer(text=f"Bot ID: {bot.user.id}")
        return embed

    @app_commands.command(name="botinfo", description="Show information about this bot")
    async def botinfo_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not self.bot.application:
            await self.bot.application_info()
        embed = self.build_embed()
        await interaction.followup.send(embed=embed)

    @commands.command(name="botinfo")
    async def botinfo_prefix(self, ctx: commands.Context):
        if not self.bot.application:
            await self.bot.application_info()
        embed = self.build_embed()
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(BotInfo(bot))
