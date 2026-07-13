import discord
from discord.ext import commands
import os
import asyncio
import logging
from utils.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("KapiBot")

COGS = [
    "cogs.economy",
    "cogs.levels",
    "cogs.gacha",
    "cogs.roles",
    "cogs.tickets",
    "cogs.moderation",
    "cogs.logging",
    "cogs.welcome",
    "cogs.settings",
    "cogs.gambling",
]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.presences = False


class KapiBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="kapi ",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        await init_db()
        for cog in COGS:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")

    async def on_ready(self):
        logger.info(f"KapiBot is online as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="kapi help",
            )
        )

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ 引数が足りません。`kapi help {ctx.command}`で使い方を確認してください。")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ あなたにはこのコマンドを使う権限がありません。")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ Botに必要な権限がありません。")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ クールダウン中です。{error.retry_after:.1f}秒後に再試行してください。")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ 引数が無効です: {error}")
        else:
            logger.error(f"Unhandled error in {ctx.command}: {error}")
            await ctx.send(f"❌ エラーが発生しました: {error}")


def clean_token(token: str) -> str:
    CYRILLIC_MAP = {
        'А': 'A', 'В': 'B', 'С': 'C', 'Е': 'E', 'Н': 'H', 'І': 'I',
        'К': 'K', 'М': 'M', 'О': 'O', 'Р': 'P', 'Т': 'T', 'Х': 'X',
        'а': 'a', 'с': 'c', 'е': 'e', 'о': 'o', 'р': 'p', 'х': 'x',
        'у': 'y', 'і': 'i',
    }
    # Remove any whitespace, newlines, pipes and other non-token chars
    VALID_CHARS = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-')
    cleaned = ''.join(CYRILLIC_MAP.get(c, c) for c in token)
    cleaned = ''.join(c for c in cleaned if c in VALID_CHARS)
    logger.info(f"Token cleaned: {len(token)} → {len(cleaned)} chars")
    return cleaned


async def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN が設定されていません。")
        return
    token = clean_token(token)
    bot = KapiBot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
