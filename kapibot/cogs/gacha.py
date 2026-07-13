import discord
from discord.ext import commands
import aiosqlite
import random
from utils.database import DB_PATH
from utils.helpers import make_embed, format_number

RARITY_COLORS = {
    "N": discord.Color.light_gray(),
    "R": discord.Color.blue(),
    "SR": discord.Color.purple(),
    "SSR": discord.Color.gold(),
    "UR": discord.Color.red(),
}

RARITY_EMOJI = {
    "N": "⚪",
    "R": "🔵",
    "SR": "🟣",
    "SSR": "🟡",
    "UR": "🔴",
}

GACHA_COST = 100


class Gacha(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def roll_item(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, name, rarity, weight, role_id, description FROM gacha_items WHERE guild_id=?",
                (guild_id,),
            ) as cur:
                items = await cur.fetchall()

        if not items:
            return None

        weights = [item[3] for item in items]
        chosen = random.choices(items, weights=weights, k=1)[0]
        return chosen

    @commands.command(name="gacha", aliases=["ガチャ"])
    async def gacha(self, ctx):
        """ガチャを1回引きます（100 Kapi Coin）"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT balance FROM economy WHERE user_id=? AND guild_id=?",
                (ctx.author.id, ctx.guild.id),
            ) as cur:
                row = await cur.fetchone()

        balance = row[0] if row else 0
        if balance < GACHA_COST:
            await ctx.send(
                embed=make_embed(
                    description=f"ガチャには **{GACHA_COST} Kapi Coin** 必要です。現在の残高: **{format_number(balance)}**",
                    color=discord.Color.red(),
                )
            )
            return

        item = await self.roll_item(ctx.guild.id)
        if not item:
            await ctx.send(
                embed=make_embed(
                    description="ガチャアイテムがまだ設定されていません。管理者に連絡してください。",
                    color=discord.Color.orange(),
                )
            )
            return

        item_id, name, rarity, weight, role_id, description = item

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE economy SET balance = balance - ? WHERE user_id=? AND guild_id=?",
                (GACHA_COST, ctx.author.id, ctx.guild.id),
            )
            await db.execute(
                """INSERT INTO gacha_inventory (user_id, guild_id, item_id, quantity)
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

        color = RARITY_COLORS.get(rarity, discord.Color.blurple())
        emoji = RARITY_EMOJI.get(rarity, "⚪")

        embed = make_embed(
            title=f"🎰 ガチャ結果！",
            description=f"{emoji} **[{rarity}] {name}**\n\n{description or ''}",
            color=color,
            footer=f"-{GACHA_COST} Kapi Coin | 残高: {format_number(balance - GACHA_COST)} Kapi Coin",
            thumbnail=ctx.author.display_avatar.url,
            timestamp=True,
        )
        await ctx.send(embed=embed)

    @commands.command(name="gacha10", aliases=["ガチャ10連"])
    async def gacha10(self, ctx):
        """ガチャを10回引きます（900 Kapi Coin・10%割引）"""
        cost = GACHA_COST * 10 * 9 // 10
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT balance FROM economy WHERE user_id=? AND guild_id=?",
                (ctx.author.id, ctx.guild.id),
            ) as cur:
                row = await cur.fetchone()

        balance = row[0] if row else 0
        if balance < cost:
            await ctx.send(
                embed=make_embed(
                    description=f"10連ガチャには **{cost} Kapi Coin** 必要です。現在の残高: **{format_number(balance)}**",
                    color=discord.Color.red(),
                )
            )
            return

        results = []
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE economy SET balance = balance - ? WHERE user_id=? AND guild_id=?",
                (cost, ctx.author.id, ctx.guild.id),
            )
            for _ in range(10):
                item = await self.roll_item(ctx.guild.id)
                if not item:
                    break
                item_id, name, rarity, weight, role_id, description = item
                results.append((item_id, name, rarity, role_id))
                await db.execute(
                    """INSERT INTO gacha_inventory (user_id, guild_id, item_id, quantity)
                       VALUES (?, ?, ?, 1)
                       ON CONFLICT(user_id, guild_id, item_id) DO UPDATE SET quantity = quantity + 1""",
                    (ctx.author.id, ctx.guild.id, item_id),
                )
            await db.commit()

        for item_id, name, rarity, role_id in results:
            if role_id:
                role = ctx.guild.get_role(role_id)
                if role:
                    try:
                        await ctx.author.add_roles(role)
                    except discord.Forbidden:
                        pass

        lines = [f"{RARITY_EMOJI.get(r, '⚪')} **[{r}] {n}**" for _, n, r, _ in results]
        embed = make_embed(
            title="🎰 10連ガチャ結果！",
            description="\n".join(lines),
            color=discord.Color.gold(),
            footer=f"-{cost} Kapi Coin | 残高: {format_number(balance - cost)} Kapi Coin",
            timestamp=True,
        )
        await ctx.send(embed=embed)

    @commands.command(name="gachalist", aliases=["ガチャリスト"])
    async def gachalist(self, ctx):
        """ガチャのアイテム一覧を表示します"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT name, rarity, description FROM gacha_items WHERE guild_id=? ORDER BY weight DESC",
                (ctx.guild.id,),
            ) as cur:
                items = await cur.fetchall()

        if not items:
            await ctx.send(
                embed=make_embed(
                    title="🎰 ガチャアイテム一覧",
                    description="まだアイテムが設定されていません。",
                    color=discord.Color.blue(),
                )
            )
            return

        embed = make_embed(title="🎰 ガチャアイテム一覧", color=discord.Color.purple())
        for name, rarity, desc in items:
            emoji = RARITY_EMOJI.get(rarity, "⚪")
            embed.add_field(
                name=f"{emoji} [{rarity}] {name}",
                value=desc or "説明なし",
                inline=False,
            )
        embed.set_footer(text=f"1回 {GACHA_COST} Kapi Coin | 10連 {GACHA_COST*10*9//10} Kapi Coin（10%割引）")
        await ctx.send(embed=embed)

    @commands.command(name="gachainv", aliases=["ガチャインベントリ"])
    async def gachainv(self, ctx, member: discord.Member = None):
        """ガチャで入手したアイテム一覧を表示します"""
        member = member or ctx.author
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """SELECT g.name, g.rarity, gi.quantity
                   FROM gacha_inventory gi
                   JOIN gacha_items g ON gi.item_id = g.id
                   WHERE gi.user_id=? AND gi.guild_id=?
                   ORDER BY g.rarity""",
                (member.id, ctx.guild.id),
            ) as cur:
                items = await cur.fetchall()

        if not items:
            await ctx.send(
                embed=make_embed(
                    title=f"🎴 {member.display_name} のガチャコレクション",
                    description="まだアイテムを持っていません。",
                    color=discord.Color.blue(),
                )
            )
            return

        lines = [f"{RARITY_EMOJI.get(r,'⚪')} **[{r}] {n}** x{q}" for n, r, q in items]
        embed = make_embed(
            title=f"🎴 {member.display_name} のガチャコレクション",
            description="\n".join(lines),
            color=discord.Color.purple(),
            thumbnail=member.display_avatar.url,
        )
        await ctx.send(embed=embed)

    @commands.command(name="addgacha")
    @commands.has_permissions(administrator=True)
    async def addgacha(self, ctx, rarity: str, weight: int, role: discord.Role = None, *, name: str):
        """ガチャアイテムを追加します（管理者専用）\n例: kapi addgacha SSR 5 @ロール アイテム名"""
        rarity = rarity.upper()
        if rarity not in RARITY_COLORS:
            await ctx.send(
                embed=make_embed(
                    description=f"レアリティは N, R, SR, SSR, UR のいずれかを指定してください。",
                    color=discord.Color.red(),
                )
            )
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO gacha_items (guild_id, name, rarity, weight, role_id) VALUES (?, ?, ?, ?, ?)",
                (ctx.guild.id, name, rarity, weight, role.id if role else None),
            )
            await db.commit()
        embed = make_embed(
            description=f"{RARITY_EMOJI[rarity]} **[{rarity}] {name}** をガチャに追加しました。（重み: {weight}）",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="removegacha")
    @commands.has_permissions(administrator=True)
    async def removegacha(self, ctx, item_id: int):
        """ガチャアイテムを削除します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM gacha_items WHERE id=? AND guild_id=?", (item_id, ctx.guild.id))
            await db.commit()
        await ctx.send(embed=make_embed(description=f"ガチャアイテム #{item_id} を削除しました。", color=discord.Color.green()))


async def setup(bot):
    await bot.add_cog(Gacha(bot))
