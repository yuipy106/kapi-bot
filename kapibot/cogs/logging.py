import discord
from discord.ext import commands
import aiosqlite
from utils.database import DB_PATH
from utils.helpers import make_embed


class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_log_channel(self, guild: discord.Guild):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT log_channel_id FROM guild_settings WHERE guild_id=?",
                (guild.id,),
            ) as cur:
                row = await cur.fetchone()
        if row and row[0]:
            return guild.get_channel(row[0])
        return None

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        channel = await self.get_log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        embed = make_embed(
            title="🗑️ メッセージ削除",
            color=discord.Color.red(),
            timestamp=True,
        )
        embed.add_field(name="送信者", value=message.author.mention, inline=True)
        embed.add_field(name="チャンネル", value=message.channel.mention, inline=True)
        embed.add_field(name="内容", value=message.content[:1024] or "*(空またはメディア)*", inline=False)
        embed.set_thumbnail(url=message.author.display_avatar.url)
        await self.send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = make_embed(
            title="✏️ メッセージ編集",
            color=discord.Color.orange(),
            timestamp=True,
        )
        embed.add_field(name="送信者", value=before.author.mention, inline=True)
        embed.add_field(name="チャンネル", value=before.channel.mention, inline=True)
        embed.add_field(name="編集前", value=before.content[:512] or "*(空)*", inline=False)
        embed.add_field(name="編集後", value=after.content[:512] or "*(空)*", inline=False)
        embed.set_thumbnail(url=before.author.display_avatar.url)
        await self.send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = make_embed(
            title="📥 メンバー参加",
            description=f"{member.mention} ({member}) がサーバーに参加しました。",
            color=discord.Color.green(),
            timestamp=True,
        )
        embed.add_field(name="アカウント作成日", value=member.created_at.strftime("%Y/%m/%d"), inline=True)
        embed.add_field(name="メンバー数", value=str(member.guild.member_count), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = make_embed(
            title="📤 メンバー退出",
            description=f"{member.mention} ({member}) がサーバーから退出しました。",
            color=discord.Color.red(),
            timestamp=True,
        )
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed.add_field(name="ロール", value=", ".join(roles) or "なし", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles and before.nick == after.nick:
            return

        embed = make_embed(
            title="👤 メンバー更新",
            color=discord.Color.blurple(),
            timestamp=True,
        )
        embed.set_thumbnail(url=after.display_avatar.url)

        if before.nick != after.nick:
            embed.add_field(name="ニックネーム変更", value=f"{before.nick or before.name} → {after.nick or after.name}", inline=False)

        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added:
            embed.add_field(name="ロール追加", value=", ".join(r.mention for r in added), inline=False)
        if removed:
            embed.add_field(name="ロール削除", value=", ".join(r.mention for r in removed), inline=False)

        if embed.fields:
            embed.description = f"対象: {after.mention}"
            await self.send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        embed = make_embed(
            title="📢 チャンネル作成",
            description=f"**{channel.name}** ({channel.mention}) が作成されました。",
            color=discord.Color.green(),
            timestamp=True,
        )
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        embed = make_embed(
            title="🗑️ チャンネル削除",
            description=f"**{channel.name}** が削除されました。",
            color=discord.Color.red(),
            timestamp=True,
        )
        await self.send_log(channel.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = make_embed(
            title="🔖 ロール作成",
            description=f"ロール **{role.name}** が作成されました。",
            color=discord.Color.green(),
            timestamp=True,
        )
        await self.send_log(role.guild, embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = make_embed(
            title="🔖 ロール削除",
            description=f"ロール **{role.name}** が削除されました。",
            color=discord.Color.red(),
            timestamp=True,
        )
        await self.send_log(role.guild, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return

        if before.channel is None and after.channel:
            desc = f"{member.mention} が **{after.channel.name}** に参加しました。"
            color = discord.Color.green()
        elif before.channel and after.channel is None:
            desc = f"{member.mention} が **{before.channel.name}** から退出しました。"
            color = discord.Color.red()
        else:
            desc = f"{member.mention} が **{before.channel.name}** → **{after.channel.name}** に移動しました。"
            color = discord.Color.blue()

        embed = make_embed(title="🔊 ボイスチャンネル更新", description=desc, color=color, timestamp=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.send_log(member.guild, embed)

    @commands.command(name="setlog", aliases=["ログ設定"])
    @commands.has_permissions(administrator=True)
    async def setlog(self, ctx, channel: discord.TextChannel):
        """ログチャンネルを設定します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, log_channel_id) VALUES (?, ?)",
                (ctx.guild.id, channel.id),
            )
            await db.commit()
        embed = make_embed(
            description=f"ログチャンネルを {channel.mention} に設定しました。",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Logging(bot))
