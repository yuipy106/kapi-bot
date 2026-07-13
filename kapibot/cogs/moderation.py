import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime, timedelta
from collections import defaultdict
import time
from utils.database import DB_PATH
from utils.helpers import make_embed


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {guild_id: {user_id: [timestamp, ...]}}
        self._msg_tracker: dict = defaultdict(lambda: defaultdict(list))

    async def log_action(self, guild: discord.Guild, embed: discord.Embed):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT log_channel_id FROM guild_settings WHERE guild_id=?",
                (guild.id,),
            ) as cur:
                row = await cur.fetchone()
        if row and row[0]:
            channel = guild.get_channel(row[0])
            if channel:
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    async def get_spam_settings(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT enabled, message_limit, time_window, timeout_duration FROM spam_settings WHERE guild_id=?",
                (guild_id,),
            ) as cur:
                row = await cur.fetchone()
        if row:
            return {"enabled": bool(row[0]), "limit": row[1], "window": row[2], "duration": row[3]}
        return {"enabled": True, "limit": 5, "window": 5, "duration": 60}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        member = message.author
        if member.guild_permissions.administrator:
            return

        settings = await self.get_spam_settings(message.guild.id)
        if not settings["enabled"]:
            return

        guild_id = message.guild.id
        user_id = member.id
        now = time.time()
        window = settings["window"]
        limit = settings["limit"]

        timestamps = self._msg_tracker[guild_id][user_id]
        timestamps.append(now)
        # ウィンドウ外のタイムスタンプを削除
        self._msg_tracker[guild_id][user_id] = [t for t in timestamps if now - t <= window]

        if len(self._msg_tracker[guild_id][user_id]) >= limit:
            # タイムスタンプをリセットして二重タイムアウトを防ぐ
            self._msg_tracker[guild_id][user_id] = []
            duration = settings["duration"]
            until = discord.utils.utcnow() + timedelta(seconds=duration)
            try:
                await member.timeout(until, reason=f"自動スパム検出: {window}秒以内に{limit}回以上メッセージ送信")
                mins = duration // 60
                secs = duration % 60
                dur_str = f"{mins}分" if secs == 0 else f"{mins}分{secs}秒" if mins else f"{secs}秒"
                alert = await message.channel.send(
                    embed=make_embed(
                        title="🤖 自動スパム検出",
                        description=f"{member.mention} がスパムとして検出されました。\n**{dur_str}間**タイムアウトされました。",
                        color=discord.Color.red(),
                        footer=f"設定: {window}秒以内に{limit}回 | kapi antispam で設定変更",
                    )
                )
                import asyncio
                await asyncio.sleep(8)
                try:
                    await alert.delete()
                except Exception:
                    pass

                log_embed = make_embed(
                    title="🤖 自動スパム検出 — タイムアウト",
                    description=f"**対象:** {member.mention} ({member})\n**チャンネル:** {message.channel.mention}\n**期間:** {dur_str}\n**理由:** {window}秒以内に{limit}回以上メッセージ送信",
                    color=discord.Color.red(),
                    timestamp=True,
                )
                await self.log_action(message.guild, log_embed)
            except discord.Forbidden:
                pass

    @commands.command(name="antispam", aliases=["スパム設定", "spam"])
    @commands.has_permissions(administrator=True)
    async def antispam(self, ctx, enabled: str = None):
        """自動スパム検出の設定を表示・切り替えます\n使い方: kapi antispam [on/off]"""
        settings = await self.get_spam_settings(ctx.guild.id)

        if enabled is not None:
            new_state = enabled.lower() in ("on", "有効", "true", "1")
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT INTO spam_settings (guild_id, enabled) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET enabled=?",
                    (ctx.guild.id, int(new_state), int(new_state)),
                )
                await db.commit()
            state_str = "✅ 有効" if new_state else "❌ 無効"
            await ctx.send(embed=make_embed(description=f"自動スパム検出を **{state_str}** にしました。", color=discord.Color.green()))
            return

        state_str = "✅ 有効" if settings["enabled"] else "❌ 無効"
        embed = make_embed(
            title="🛡️ 自動スパム検出 設定",
            description=(
                f"**状態:** {state_str}\n"
                f"**検出条件:** {settings['window']}秒以内に{settings['limit']}回以上\n"
                f"**タイムアウト時間:** {settings['duration']}秒\n\n"
                "設定変更:\n"
                "`kapi antispam on/off` — 有効/無効\n"
                "`kapi setspam <limit> <window秒> <timeout秒>` — 閾値変更"
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="setspam", aliases=["スパム閾値設定"])
    @commands.has_permissions(administrator=True)
    async def setspam(self, ctx, limit: int, window: int, timeout_secs: int):
        """スパム検出の閾値を設定します（管理者専用）\n使い方: kapi setspam <メッセージ数> <秒数> <タイムアウト秒>\n例: kapi setspam 5 5 120 → 5秒以内に5回で2分タイムアウト"""
        if limit < 2 or limit > 30:
            await ctx.send(embed=make_embed(description="メッセージ数は2〜30で指定してください。", color=discord.Color.red()))
            return
        if window < 1 or window > 30:
            await ctx.send(embed=make_embed(description="秒数は1〜30で指定してください。", color=discord.Color.red()))
            return
        if timeout_secs < 10 or timeout_secs > 2419200:
            await ctx.send(embed=make_embed(description="タイムアウト時間は10秒〜28日で指定してください。", color=discord.Color.red()))
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO spam_settings (guild_id, message_limit, time_window, timeout_duration)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET message_limit=?, time_window=?, timeout_duration=?""",
                (ctx.guild.id, limit, window, timeout_secs, limit, window, timeout_secs),
            )
            await db.commit()

        mins = timeout_secs // 60
        secs = timeout_secs % 60
        dur_str = f"{mins}分" if secs == 0 else f"{mins}分{secs}秒" if mins else f"{secs}秒"
        await ctx.send(embed=make_embed(
            title="✅ スパム検出設定を更新しました",
            description=f"**検出条件:** {window}秒以内に{limit}回以上\n**タイムアウト時間:** {dur_str}",
            color=discord.Color.green(),
        ))

    @commands.command(name="ban", aliases=["バン"])
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "理由なし"):
        """メンバーをBANします"""
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=make_embed(description="そのメンバーをBANする権限がありません。", color=discord.Color.red()))
            return

        await member.ban(reason=f"{ctx.author}: {reason}")
        embed = make_embed(
            title="🔨 BANしました",
            description=f"**対象:** {member.mention} ({member})\n**理由:** {reason}\n**実行者:** {ctx.author.mention}",
            color=discord.Color.red(),
            timestamp=True,
        )
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, embed)

    @commands.command(name="unban", aliases=["アンバン"])
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason: str = "理由なし"):
        """BANを解除します"""
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")
            embed = make_embed(
                title="✅ BANを解除しました",
                description=f"**対象:** {user} (ID: {user_id})\n**理由:** {reason}\n**実行者:** {ctx.author.mention}",
                color=discord.Color.green(),
                timestamp=True,
            )
            await ctx.send(embed=embed)
            await self.log_action(ctx.guild, embed)
        except discord.NotFound:
            await ctx.send(embed=make_embed(description="そのユーザーはBANされていません。", color=discord.Color.red()))

    @commands.command(name="kick", aliases=["キック"])
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "理由なし"):
        """メンバーをKICKします"""
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send(embed=make_embed(description="そのメンバーをKICKする権限がありません。", color=discord.Color.red()))
            return

        await member.kick(reason=f"{ctx.author}: {reason}")
        embed = make_embed(
            title="👢 KICKしました",
            description=f"**対象:** {member.mention} ({member})\n**理由:** {reason}\n**実行者:** {ctx.author.mention}",
            color=discord.Color.orange(),
            timestamp=True,
        )
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, embed)

    @commands.command(name="timeout", aliases=["タイムアウト", "mute"])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: int, unit: str = "m", *, reason: str = "理由なし"):
        """メンバーをタイムアウトします\n例: kapi timeout @user 10 m 荒らし行為\n単位: s=秒, m=分, h=時間, d=日"""
        unit_map = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        if unit not in unit_map:
            await ctx.send(embed=make_embed(description="単位は s(秒), m(分), h(時間), d(日) を使用してください。", color=discord.Color.red()))
            return

        seconds = duration * unit_map[unit]
        if seconds > 2419200:
            await ctx.send(embed=make_embed(description="タイムアウトは最大28日間です。", color=discord.Color.red()))
            return

        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        await member.timeout(until, reason=f"{ctx.author}: {reason}")

        unit_labels = {"s": "秒", "m": "分", "h": "時間", "d": "日"}
        embed = make_embed(
            title="⏰ タイムアウトしました",
            description=f"**対象:** {member.mention} ({member})\n**期間:** {duration}{unit_labels[unit]}\n**理由:** {reason}\n**実行者:** {ctx.author.mention}",
            color=discord.Color.orange(),
            timestamp=True,
        )
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, embed)

    @commands.command(name="untimeout", aliases=["アンタイムアウト", "unmute"])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, *, reason: str = "理由なし"):
        """タイムアウトを解除します"""
        await member.timeout(None, reason=f"{ctx.author}: {reason}")
        embed = make_embed(
            title="✅ タイムアウトを解除しました",
            description=f"**対象:** {member.mention}\n**実行者:** {ctx.author.mention}",
            color=discord.Color.green(),
            timestamp=True,
        )
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, embed)

    @commands.command(name="purge", aliases=["clear", "クリア"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        """指定した数のメッセージを削除します（最大100件）"""
        if amount < 1 or amount > 100:
            await ctx.send(embed=make_embed(description="1〜100の間で指定してください。", color=discord.Color.red()))
            return

        deleted = await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(
            embed=make_embed(
                description=f"✅ {len(deleted) - 1}件のメッセージを削除しました。",
                color=discord.Color.green(),
            )
        )
        import asyncio
        await asyncio.sleep(3)
        await msg.delete()

        log_embed = make_embed(
            title="🗑️ メッセージ一括削除",
            description=f"**チャンネル:** {ctx.channel.mention}\n**件数:** {len(deleted)-1}件\n**実行者:** {ctx.author.mention}",
            color=discord.Color.orange(),
            timestamp=True,
        )
        await self.log_action(ctx.guild, log_embed)

    @commands.command(name="warn", aliases=["警告"])
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = "理由なし"):
        """メンバーに警告を与えます"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (ctx.guild.id, member.id, ctx.author.id, reason, datetime.utcnow().isoformat()),
            )
            await db.commit()
            async with db.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id=? AND user_id=?",
                (ctx.guild.id, member.id),
            ) as cur:
                count = (await cur.fetchone())[0]

        embed = make_embed(
            title="⚠️ 警告を発行しました",
            description=f"**対象:** {member.mention} ({member})\n**理由:** {reason}\n**実行者:** {ctx.author.mention}\n**累計警告数:** {count}回",
            color=discord.Color.yellow(),
            timestamp=True,
        )
        await ctx.send(embed=embed)
        await self.log_action(ctx.guild, embed)

        try:
            await member.send(
                embed=make_embed(
                    title=f"⚠️ {ctx.guild.name} で警告を受けました",
                    description=f"**理由:** {reason}\n**累計警告数:** {count}回",
                    color=discord.Color.yellow(),
                )
            )
        except discord.Forbidden:
            pass

    @commands.command(name="warnings", aliases=["warns", "警告一覧"])
    async def warnings(self, ctx, member: discord.Member = None):
        """メンバーの警告一覧を表示します"""
        member = member or ctx.author
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, moderator_id, reason, created_at FROM warnings WHERE guild_id=? AND user_id=? ORDER BY created_at DESC",
                (ctx.guild.id, member.id),
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await ctx.send(
                embed=make_embed(
                    description=f"{member.display_name} への警告はありません。",
                    color=discord.Color.green(),
                )
            )
            return

        embed = make_embed(
            title=f"⚠️ {member.display_name} の警告 ({len(rows)}件)",
            color=discord.Color.yellow(),
            thumbnail=member.display_avatar.url,
        )
        for warn_id, mod_id, reason, created_at in rows[:10]:
            mod = ctx.guild.get_member(mod_id)
            mod_name = mod.display_name if mod else f"ID:{mod_id}"
            date = created_at[:10]
            embed.add_field(
                name=f"#{warn_id} — {date}",
                value=f"**理由:** {reason}\n**発行者:** {mod_name}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="clearwarn", aliases=["警告削除"])
    @commands.has_permissions(manage_messages=True)
    async def clearwarn(self, ctx, warn_id: int):
        """特定の警告を削除します"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM warnings WHERE id=? AND guild_id=?",
                (warn_id, ctx.guild.id),
            )
            await db.commit()
        await ctx.send(embed=make_embed(description=f"警告 #{warn_id} を削除しました。", color=discord.Color.green()))

    @commands.command(name="clearallwarns", aliases=["全警告削除"])
    @commands.has_permissions(administrator=True)
    async def clearallwarns(self, ctx, member: discord.Member):
        """メンバーの全警告を削除します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM warnings WHERE guild_id=? AND user_id=?",
                (ctx.guild.id, member.id),
            )
            await db.commit()
        await ctx.send(
            embed=make_embed(
                description=f"{member.mention} の全警告を削除しました。",
                color=discord.Color.green(),
            )
        )


async def setup(bot):
    await bot.add_cog(Moderation(bot))
