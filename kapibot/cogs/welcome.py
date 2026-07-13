import discord
from discord.ext import commands
import aiosqlite
from utils.database import DB_PATH
from utils.helpers import make_embed


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_settings(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT welcome_channel_id, leave_channel_id, welcome_message, leave_message FROM guild_settings WHERE guild_id=?",
                (guild_id,),
            ) as cur:
                row = await cur.fetchone()
        if row:
            return {
                "welcome_channel_id": row[0],
                "leave_channel_id": row[1],
                "welcome_message": row[2],
                "leave_message": row[3],
            }
        return {}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        settings = await self.get_settings(member.guild.id)
        channel_id = settings.get("welcome_channel_id")
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        template = settings.get("welcome_message") or "🎉 {user} がサーバーに参加しました！ようこそ **{server}** へ！"
        msg = template.replace("{user}", member.mention).replace("{server}", member.guild.name).replace("{username}", member.name)

        embed = make_embed(
            title="👋 ようこそ！",
            description=msg,
            color=discord.Color.green(),
            thumbnail=member.display_avatar.url,
            timestamp=True,
        )
        embed.add_field(name="メンバー番号", value=f"#{member.guild.member_count}", inline=True)
        embed.add_field(name="アカウント作成日", value=member.created_at.strftime("%Y/%m/%d"), inline=True)

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        settings = await self.get_settings(member.guild.id)
        channel_id = settings.get("leave_channel_id")
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        template = settings.get("leave_message") or "👋 {username} がサーバーから退出しました。"
        msg = template.replace("{user}", member.mention).replace("{server}", member.guild.name).replace("{username}", member.name)

        embed = make_embed(
            title="👋 さようなら",
            description=msg,
            color=discord.Color.red(),
            thumbnail=member.display_avatar.url,
            timestamp=True,
        )
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.command(name="setwelcome", aliases=["歓迎設定"])
    @commands.has_permissions(administrator=True)
    async def setwelcome(self, ctx, channel: discord.TextChannel, *, message: str = None):
        """歓迎メッセージのチャンネルと内容を設定します（管理者専用）\n変数: {user} {username} {server}"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO guild_settings (guild_id, welcome_channel_id, welcome_message)
                   VALUES (?, ?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET welcome_channel_id=?, welcome_message=?""",
                (ctx.guild.id, channel.id, message, channel.id, message),
            )
            await db.commit()
        embed = make_embed(
            title="✅ 歓迎メッセージ設定完了",
            color=discord.Color.green(),
        )
        embed.add_field(name="チャンネル", value=channel.mention, inline=True)
        embed.add_field(name="メッセージ", value=message or "デフォルト", inline=False)
        embed.set_footer(text="使用できる変数: {user} {username} {server}")
        await ctx.send(embed=embed)

    @commands.command(name="setleave", aliases=["退出設定"])
    @commands.has_permissions(administrator=True)
    async def setleave(self, ctx, channel: discord.TextChannel, *, message: str = None):
        """退出メッセージのチャンネルと内容を設定します（管理者専用）\n変数: {user} {username} {server}"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO guild_settings (guild_id, leave_channel_id, leave_message)
                   VALUES (?, ?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET leave_channel_id=?, leave_message=?""",
                (ctx.guild.id, channel.id, message, channel.id, message),
            )
            await db.commit()
        embed = make_embed(
            title="✅ 退出メッセージ設定完了",
            color=discord.Color.green(),
        )
        embed.add_field(name="チャンネル", value=channel.mention, inline=True)
        embed.add_field(name="メッセージ", value=message or "デフォルト", inline=False)
        embed.set_footer(text="使用できる変数: {user} {username} {server}")
        await ctx.send(embed=embed)

    @commands.command(name="testwelcome", aliases=["歓迎テスト"])
    @commands.has_permissions(administrator=True)
    async def testwelcome(self, ctx):
        """歓迎メッセージをテスト送信します（管理者専用）"""
        await self.on_member_join(ctx.author)
        await ctx.message.add_reaction("✅")

    @commands.command(name="testleave", aliases=["退出テスト"])
    @commands.has_permissions(administrator=True)
    async def testleave(self, ctx):
        """退出メッセージをテスト送信します（管理者専用）"""
        await self.on_member_remove(ctx.author)
        await ctx.message.add_reaction("✅")


async def setup(bot):
    await bot.add_cog(Welcome(bot))
