import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime, timedelta
import random
from utils.database import DB_PATH
from utils.helpers import make_embed, xp_progress, format_number


class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._xp_cooldowns = {}

    async def get_settings(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT xp_rate, xp_cooldown, level_up_channel_id, level_up_message FROM guild_settings WHERE guild_id=?",
                (guild_id,),
            ) as cur:
                row = await cur.fetchone()
        if row:
            return {"xp_rate": row[0], "xp_cooldown": row[1], "level_up_channel_id": row[2], "level_up_message": row[3]}
        return {"xp_rate": 10, "xp_cooldown": 60, "level_up_channel_id": None, "level_up_message": None}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        settings = await self.get_settings(message.guild.id)
        key = (message.author.id, message.guild.id)
        now = datetime.utcnow()

        if key in self._xp_cooldowns:
            if (now - self._xp_cooldowns[key]).total_seconds() < settings["xp_cooldown"]:
                return

        self._xp_cooldowns[key] = now
        xp_gain = random.randint(settings["xp_rate"], settings["xp_rate"] * 2)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO levels (user_id, guild_id) VALUES (?, ?)",
                (message.author.id, message.guild.id),
            )
            await db.execute(
                "UPDATE levels SET xp = xp + ?, total_messages = total_messages + 1 WHERE user_id=? AND guild_id=?",
                (xp_gain, message.author.id, message.guild.id),
            )
            await db.commit()

            async with db.execute(
                "SELECT xp, level FROM levels WHERE user_id=? AND guild_id=?",
                (message.author.id, message.guild.id),
            ) as cur:
                row = await cur.fetchone()

        if not row:
            return

        total_xp, current_level = row
        new_level, _, _ = xp_progress(total_xp)

        if new_level > current_level:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE levels SET level=? WHERE user_id=? AND guild_id=?",
                    (new_level, message.author.id, message.guild.id),
                )
                await db.commit()

            await self.assign_level_role(message.author, message.guild, new_level)
            await self.send_level_up(message, new_level, settings)

    async def assign_level_role(self, member: discord.Member, guild: discord.Guild, level: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT role_id FROM level_roles WHERE guild_id=? AND level<=? ORDER BY level DESC",
                (guild.id, level),
            ) as cur:
                rows = await cur.fetchall()

        for (role_id,) in rows:
            role = guild.get_role(role_id)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason=f"Level {level}達成")
                except discord.Forbidden:
                    pass

    async def send_level_up(self, message: discord.Message, new_level: int, settings: dict):
        msg_template = settings.get("level_up_message") or "{user} がレベル **{level}** に上がりました！🎉"
        msg = msg_template.replace("{user}", message.author.mention).replace("{level}", str(new_level))

        channel_id = settings.get("level_up_channel_id")
        channel = message.guild.get_channel(channel_id) if channel_id else message.channel

        if channel:
            embed = make_embed(
                title="🆙 レベルアップ！",
                description=msg,
                color=discord.Color.gold(),
                thumbnail=message.author.display_avatar.url,
            )
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    @commands.command(name="rank", aliases=["level", "xp", "ランク"])
    async def rank(self, ctx, member: discord.Member = None):
        """自分またはメンバーのランクを確認します"""
        member = member or ctx.author
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT xp, level, total_messages FROM levels WHERE user_id=? AND guild_id=?",
                (member.id, ctx.guild.id),
            ) as cur:
                row = await cur.fetchone()

        if not row:
            await ctx.send(
                embed=make_embed(
                    description=f"{member.display_name} はまだメッセージを送っていません。",
                    color=discord.Color.red(),
                )
            )
            return

        total_xp, level, total_msgs = row
        _, current_xp, needed_xp = xp_progress(total_xp)

        bar_filled = int((current_xp / needed_xp) * 20) if needed_xp > 0 else 20
        bar = "█" * bar_filled + "░" * (20 - bar_filled)

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM levels WHERE guild_id=? AND xp > ?",
                (ctx.guild.id, total_xp),
            ) as cur:
                rank_row = await cur.fetchone()

        rank_pos = (rank_row[0] if rank_row else 0) + 1

        embed = make_embed(
            title=f"📊 {member.display_name} のランク",
            color=discord.Color.blurple(),
            thumbnail=member.display_avatar.url,
        )
        embed.add_field(name="レベル", value=f"**{level}**", inline=True)
        embed.add_field(name="サーバー順位", value=f"**#{rank_pos}**", inline=True)
        embed.add_field(name="総メッセージ数", value=f"**{format_number(total_msgs)}**", inline=True)
        embed.add_field(
            name=f"XP: {format_number(current_xp)} / {format_number(needed_xp)}",
            value=f"`{bar}`",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.command(name="levelboard", aliases=["lvlb", "レベルランキング"])
    async def levelboard(self, ctx):
        """レベルランキングを表示します"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, level, xp FROM levels WHERE guild_id=? ORDER BY xp DESC LIMIT 10",
                (ctx.guild.id,),
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await ctx.send(embed=make_embed(description="まだデータがありません。", color=discord.Color.blue()))
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, level, xp) in enumerate(rows):
            member = ctx.guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            medal = medals[i] if i < 3 else f"**#{i+1}**"
            lines.append(f"{medal} {name} — Lv.**{level}** ({format_number(xp)} XP)")

        embed = make_embed(
            title="🏆 レベルランキング",
            description="\n".join(lines),
            color=discord.Color.purple(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="setlevelrole", aliases=["レベルロール設定"])
    @commands.has_permissions(administrator=True)
    async def setlevelrole(self, ctx, level: int, role: discord.Role):
        """特定レベルに達したときに付与するロールを設定します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)",
                (ctx.guild.id, level, role.id),
            )
            await db.commit()
        embed = make_embed(
            description=f"レベル **{level}** 達成で {role.mention} が付与されるように設定しました。",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="removelevelrole")
    @commands.has_permissions(administrator=True)
    async def removelevelrole(self, ctx, level: int):
        """レベルロールの設定を削除します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM level_roles WHERE guild_id=? AND level=?",
                (ctx.guild.id, level),
            )
            await db.commit()
        await ctx.send(embed=make_embed(description=f"レベル {level} のロール設定を削除しました。", color=discord.Color.green()))

    @commands.command(name="setxp")
    @commands.has_permissions(administrator=True)
    async def setxp(self, ctx, member: discord.Member, xp: int):
        """メンバーのXPを手動設定します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO levels (user_id, guild_id, xp, level) VALUES (?, ?, ?, 0)",
                (member.id, ctx.guild.id, xp),
            )
            await db.commit()
        await ctx.send(
            embed=make_embed(
                description=f"{member.mention} のXPを **{format_number(xp)}** に設定しました。",
                color=discord.Color.green(),
            )
        )


async def setup(bot):
    await bot.add_cog(Levels(bot))
