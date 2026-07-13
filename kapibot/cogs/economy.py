import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime, timedelta
import random
from utils.database import DB_PATH
from utils.helpers import make_embed, format_number


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def ensure_user(self, user_id: int, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?, ?)",
                (user_id, guild_id),
            )
            await db.commit()

    async def get_balance(self, user_id: int, guild_id: int) -> int:
        await self.ensure_user(user_id, guild_id)
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT balance FROM economy WHERE user_id=? AND guild_id=?",
                (user_id, guild_id),
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    async def add_balance(self, user_id: int, guild_id: int, amount: int):
        await self.ensure_user(user_id, guild_id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE economy SET balance = balance + ? WHERE user_id=? AND guild_id=?",
                (amount, user_id, guild_id),
            )
            await db.commit()

    @commands.command(name="balance", aliases=["bal", "cash", "所持金", "残高"])
    async def balance(self, ctx, member: discord.Member = None):
        """Kapi Coinの残高を確認します"""
        member = member or ctx.author
        bal = await self.get_balance(member.id, ctx.guild.id)
        embed = make_embed(
            title=f"💰 {member.display_name} の残高",
            description=f"**{format_number(bal)} Kapi Coin**",
            color=discord.Color.gold(),
            thumbnail=member.display_avatar.url,
        )
        await ctx.send(embed=embed)

    @commands.command(name="daily", aliases=["デイリー"])
    @commands.cooldown(1, 1, commands.BucketType.user)
    async def daily(self, ctx):
        """毎日1回Kapi Coinをもらえます"""
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        await self.ensure_user(user_id, guild_id)

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT last_daily FROM economy WHERE user_id=? AND guild_id=?",
                (user_id, guild_id),
            ) as cur:
                row = await cur.fetchone()
                last = row[0] if row else None

        now = datetime.utcnow()
        if last:
            last_dt = datetime.fromisoformat(last)
            next_dt = last_dt + timedelta(days=1)
            if now < next_dt:
                remaining = next_dt - now
                hours, rem = divmod(int(remaining.total_seconds()), 3600)
                minutes = rem // 60
                await ctx.send(
                    embed=make_embed(
                        title="⏳ デイリーはまだ受け取れません",
                        description=f"次のデイリーまで **{hours}時間{minutes}分** です。",
                        color=discord.Color.red(),
                    )
                )
                return

        streak_bonus = random.randint(100, 300)
        amount = 500 + streak_bonus
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE economy SET balance = balance + ?, last_daily = ? WHERE user_id=? AND guild_id=?",
                (amount, now.isoformat(), user_id, guild_id),
            )
            await db.commit()

        capybara_images = [
            "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Hydrochoerus_hydrochaeris_in_brazil.jpg/320px-Hydrochoerus_hydrochaeris_in_brazil.jpg",
            "https://upload.wikimedia.org/wikipedia/commons/thumb/3/35/Capybara_pair.JPG/320px-Capybara_pair.JPG",
            "https://upload.wikimedia.org/wikipedia/commons/e/ec/Capybara_Hattiesburg_Zoo_%2870909b-42%29_2560x1600.jpg",
            "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fb/Capybara_Feeding.jpg/320px-Capybara_Feeding.jpg",
        ]
        embed = make_embed(
            title="✅ デイリーボーナス受け取り完了！",
            description=f"**+{format_number(amount)} Kapi Coin** をゲットしました！",
            color=discord.Color.green(),
            footer="明日もまた受け取れます",
            timestamp=True,
        )
        embed.set_thumbnail(url=random.choice(capybara_images))
        await ctx.send(embed=embed)

    @commands.command(name="work", aliases=["仕事"])
    @commands.cooldown(1, 3600, commands.BucketType.user)
    async def work(self, ctx):
        """1時間に1回お仕事をしてKapi Coinを稼げます"""
        jobs = [
            ("プログラマー", 150, 350),
            ("料理人", 100, 280),
            ("教師", 120, 300),
            ("医者", 200, 450),
            ("配達員", 80, 220),
            ("デザイナー", 130, 320),
            ("漁師", 90, 250),
            ("農家", 70, 200),
            ("歌手", 100, 500),
            ("探偵", 160, 380),
        ]
        job_name, low, high = random.choice(jobs)
        amount = random.randint(low, high)
        await self.add_balance(ctx.author.id, ctx.guild.id, amount)

        embed = make_embed(
            title="💼 お仕事完了！",
            description=f"**{job_name}** として働いて **+{format_number(amount)} Kapi Coin** を稼ぎました！",
            color=discord.Color.green(),
            footer="次のお仕事は1時間後",
        )
        await ctx.send(embed=embed)

    @commands.command(name="pay", aliases=["送金"])
    async def pay(self, ctx, member: discord.Member, amount: int):
        """他のユーザーにKapi Coinを送金します"""
        if member == ctx.author:
            await ctx.send(embed=make_embed(description="自分自身には送金できません。", color=discord.Color.red()))
            return
        if amount <= 0:
            await ctx.send(embed=make_embed(description="1以上の金額を指定してください。", color=discord.Color.red()))
            return

        bal = await self.get_balance(ctx.author.id, ctx.guild.id)
        if bal < amount:
            await ctx.send(
                embed=make_embed(
                    description=f"残高が不足しています。現在の残高: **{format_number(bal)} Kapi Coin**",
                    color=discord.Color.red(),
                )
            )
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE economy SET balance = balance - ? WHERE user_id=? AND guild_id=?",
                (amount, ctx.author.id, ctx.guild.id),
            )
            await db.execute(
                "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?, ?)",
                (member.id, ctx.guild.id),
            )
            await db.execute(
                "UPDATE economy SET balance = balance + ? WHERE user_id=? AND guild_id=?",
                (amount, member.id, ctx.guild.id),
            )
            await db.commit()

        embed = make_embed(
            title="💸 送金完了",
            description=f"{ctx.author.mention} → {member.mention}\n**{format_number(amount)} Kapi Coin** を送金しました！",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="shop", aliases=["ショップ"])
    async def shop(self, ctx):
        """ショップのアイテム一覧を表示します"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, name, price, description FROM shop WHERE guild_id=?",
                (ctx.guild.id,),
            ) as cur:
                items = await cur.fetchall()

        if not items:
            await ctx.send(
                embed=make_embed(
                    title="🛒 ショップ",
                    description="現在ショップにアイテムがありません。\n管理者が `kapi additem` でアイテムを追加できます。",
                    color=discord.Color.blue(),
                )
            )
            return

        embed = make_embed(title="🛒 ショップ", color=discord.Color.blue())
        for item_id, name, price, desc in items:
            embed.add_field(
                name=f"#{item_id} {name} — {format_number(price)} Kapi Coin",
                value=desc or "説明なし",
                inline=False,
            )
        embed.set_footer(text="kapi buy <ID> で購入できます")
        await ctx.send(embed=embed)

    @commands.command(name="buy", aliases=["購入"])
    async def buy(self, ctx, item_id: int):
        """ショップからアイテムを購入します"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT name, price, role_id FROM shop WHERE id=? AND guild_id=?",
                (item_id, ctx.guild.id),
            ) as cur:
                item = await cur.fetchone()

        if not item:
            await ctx.send(embed=make_embed(description="そのアイテムは存在しません。", color=discord.Color.red()))
            return

        name, price, role_id = item
        bal = await self.get_balance(ctx.author.id, ctx.guild.id)
        if bal < price:
            await ctx.send(
                embed=make_embed(
                    description=f"残高が不足しています。必要: **{format_number(price)}** / 現在: **{format_number(bal)}** Kapi Coin",
                    color=discord.Color.red(),
                )
            )
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE economy SET balance = balance - ? WHERE user_id=? AND guild_id=?",
                (price, ctx.author.id, ctx.guild.id),
            )
            await db.execute(
                """INSERT INTO inventory (user_id, guild_id, item_id, quantity)
                   VALUES (?, ?, ?, 1)
                   ON CONFLICT(user_id, guild_id, item_id) DO UPDATE SET quantity = quantity + 1""",
                (ctx.author.id, ctx.guild.id, item_id),
            )
            await db.commit()

        if role_id:
            role = ctx.guild.get_role(role_id)
            if role:
                try:
                    await ctx.author.add_roles(role)
                except discord.Forbidden:
                    pass

        embed = make_embed(
            title="✅ 購入完了",
            description=f"**{name}** を購入しました！ (-{format_number(price)} Kapi Coin)",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="sell", aliases=["売却"])
    async def sell(self, ctx, item_id: int, quantity: int = 1):
        """インベントリのアイテムを売却します（購入価格の50%で）"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT name, price FROM shop WHERE id=? AND guild_id=?",
                (item_id, ctx.guild.id),
            ) as cur:
                item = await db.execute(
                    "SELECT name, price FROM shop WHERE id=? AND guild_id=?",
                    (item_id, ctx.guild.id),
                )
                item = await item.fetchone()

            if not item:
                await ctx.send(embed=make_embed(description="そのアイテムは存在しません。", color=discord.Color.red()))
                return

            name, price = item
            async with db.execute(
                "SELECT quantity FROM inventory WHERE user_id=? AND guild_id=? AND item_id=?",
                (ctx.author.id, ctx.guild.id, item_id),
            ) as cur:
                inv = await cur.fetchone()

        if not inv or inv[0] < quantity:
            await ctx.send(embed=make_embed(description="そのアイテムを十分に持っていません。", color=discord.Color.red()))
            return

        sell_price = (price // 2) * quantity
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE economy SET balance = balance + ? WHERE user_id=? AND guild_id=?",
                (sell_price, ctx.author.id, ctx.guild.id),
            )
            new_qty = inv[0] - quantity
            if new_qty <= 0:
                await db.execute(
                    "DELETE FROM inventory WHERE user_id=? AND guild_id=? AND item_id=?",
                    (ctx.author.id, ctx.guild.id, item_id),
                )
            else:
                await db.execute(
                    "UPDATE inventory SET quantity=? WHERE user_id=? AND guild_id=? AND item_id=?",
                    (new_qty, ctx.author.id, ctx.guild.id, item_id),
                )
            await db.commit()

        embed = make_embed(
            title="💰 売却完了",
            description=f"**{name}** x{quantity} を売却して **+{format_number(sell_price)} Kapi Coin** 獲得！",
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="inventory", aliases=["inv", "インベントリ"])
    async def inventory(self, ctx, member: discord.Member = None):
        """インベントリを確認します"""
        member = member or ctx.author
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """SELECT s.name, i.quantity FROM inventory i
                   JOIN shop s ON i.item_id = s.id
                   WHERE i.user_id=? AND i.guild_id=?""",
                (member.id, ctx.guild.id),
            ) as cur:
                items = await cur.fetchall()

        if not items:
            await ctx.send(
                embed=make_embed(
                    title=f"🎒 {member.display_name} のインベントリ",
                    description="アイテムがありません。",
                    color=discord.Color.blue(),
                )
            )
            return

        desc = "\n".join(f"**{name}** x{qty}" for name, qty in items)
        embed = make_embed(
            title=f"🎒 {member.display_name} のインベントリ",
            description=desc,
            color=discord.Color.blue(),
            thumbnail=member.display_avatar.url,
        )
        await ctx.send(embed=embed)

    @commands.command(name="additem")
    @commands.has_permissions(administrator=True)
    async def additem(self, ctx, price: int, role: discord.Role = None, *, name: str):
        """ショップにアイテムを追加します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO shop (guild_id, name, price, role_id) VALUES (?, ?, ?, ?)",
                (ctx.guild.id, name, price, role.id if role else None),
            )
            await db.commit()
        embed = make_embed(
            title="✅ アイテム追加",
            description=f"**{name}** ({format_number(price)} Kapi Coin) をショップに追加しました。",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="removeitem")
    @commands.has_permissions(administrator=True)
    async def removeitem(self, ctx, item_id: int):
        """ショップからアイテムを削除します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM shop WHERE id=? AND guild_id=?", (item_id, ctx.guild.id))
            await db.commit()
        await ctx.send(embed=make_embed(description=f"アイテム #{item_id} を削除しました。", color=discord.Color.green()))

    @commands.command(name="leaderboard", aliases=["lb", "ランキング"])
    async def leaderboard(self, ctx):
        """Kapi Coinのランキングを表示します"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, balance FROM economy WHERE guild_id=? ORDER BY balance DESC LIMIT 10",
                (ctx.guild.id,),
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await ctx.send(embed=make_embed(description="まだデータがありません。", color=discord.Color.blue()))
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, bal) in enumerate(rows):
            member = ctx.guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            medal = medals[i] if i < 3 else f"**#{i+1}**"
            lines.append(f"{medal} {name} — {format_number(bal)} Kapi Coin")

        embed = make_embed(
            title="🏆 Kapi Coin ランキング",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    @work.error
    async def work_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            minutes = int(error.retry_after // 60)
            seconds = int(error.retry_after % 60)
            await ctx.send(
                embed=make_embed(
                    description=f"⏳ 次のお仕事まで **{minutes}分{seconds}秒** です。",
                    color=discord.Color.orange(),
                )
            )


async def setup(bot):
    await bot.add_cog(Economy(bot))
