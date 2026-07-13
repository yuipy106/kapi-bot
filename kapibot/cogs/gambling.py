import discord
from discord.ext import commands
import random
from utils.database import DB_PATH
from utils.helpers import make_embed, format_number
import aiosqlite


class Gambling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_balance(self, user_id: int, guild_id: int) -> int:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?, ?)",
                (user_id, guild_id),
            )
            await db.commit()
            async with db.execute(
                "SELECT balance FROM economy WHERE user_id=? AND guild_id=?",
                (user_id, guild_id),
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else 0

    async def update_balance(self, user_id: int, guild_id: int, amount: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE economy SET balance = balance + ? WHERE user_id=? AND guild_id=?",
                (amount, user_id, guild_id),
            )
            await db.commit()

    def parse_bet(self, bet_str: str, balance: int) -> int | None:
        bet_str = bet_str.lower().strip()
        if bet_str in ("all", "全額", "オール"):
            return balance
        if bet_str in ("half", "半分"):
            return balance // 2
        try:
            return int(bet_str)
        except ValueError:
            return None

    # ─── コインフリップ ───────────────────────────────────────────

    @commands.command(name="coinflip", aliases=["cf", "コインフリップ", "coin"])
    async def coinflip(self, ctx, bet: str, choice: str = "表"):
        """コインを投げてKapi Coinを賭けます\n使い方: kapi coinflip <賭け金> <表/裏>\n例: kapi coinflip 100 表"""
        balance = await self.get_balance(ctx.author.id, ctx.guild.id)
        amount = self.parse_bet(bet, balance)

        if amount is None:
            await ctx.send(embed=make_embed(description="賭け金を正しく指定してください。（例: `100`, `all`, `half`）", color=discord.Color.red()))
            return
        if amount <= 0:
            await ctx.send(embed=make_embed(description="1以上の金額を指定してください。", color=discord.Color.red()))
            return
        if amount > balance:
            await ctx.send(embed=make_embed(description=f"残高が不足しています。現在: **{format_number(balance)} Kapi Coin**", color=discord.Color.red()))
            return

        choice = choice.lower()
        heads_aliases = {"表", "h", "head", "heads", "おもて"}
        tails_aliases = {"裏", "t", "tail", "tails", "うら"}
        if choice in heads_aliases:
            user_choice = "表"
        elif choice in tails_aliases:
            user_choice = "裏"
        else:
            await ctx.send(embed=make_embed(description="`表` または `裏` を指定してください。", color=discord.Color.red()))
            return

        result = random.choice(["表", "裏"])
        win = result == user_choice

        if win:
            await self.update_balance(ctx.author.id, ctx.guild.id, amount)
            embed = make_embed(
                title="🪙 コインフリップ — 勝利！",
                description=f"コインは **{result}** でした！\n**+{format_number(amount)} Kapi Coin** 獲得！",
                color=discord.Color.green(),
                footer=f"残高: {format_number(balance + amount)} Kapi Coin",
            )
        else:
            await self.update_balance(ctx.author.id, ctx.guild.id, -amount)
            embed = make_embed(
                title="🪙 コインフリップ — 敗北...",
                description=f"コインは **{result}** でした...\n**-{format_number(amount)} Kapi Coin**",
                color=discord.Color.red(),
                footer=f"残高: {format_number(balance - amount)} Kapi Coin",
            )
        await ctx.send(embed=embed)

    # ─── ダイスロール ────────────────────────────────────────────

    @commands.command(name="dice", aliases=["サイコロ", "roll"])
    async def dice(self, ctx, bet: str, number: int = None):
        """サイコロを振ってKapi Coinを賭けます（1〜6を当てると5倍）\n使い方: kapi dice <賭け金> [1-6の数字]"""
        balance = await self.get_balance(ctx.author.id, ctx.guild.id)
        amount = self.parse_bet(bet, balance)

        if amount is None:
            await ctx.send(embed=make_embed(description="賭け金を正しく指定してください。", color=discord.Color.red()))
            return
        if amount <= 0 or amount > balance:
            await ctx.send(embed=make_embed(description=f"賭け金が無効です。残高: **{format_number(balance)} Kapi Coin**", color=discord.Color.red()))
            return

        result = random.randint(1, 6)
        dice_emojis = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

        if number is not None:
            # 数字を当てる (5倍)
            if number < 1 or number > 6:
                await ctx.send(embed=make_embed(description="1〜6の数字を指定してください。", color=discord.Color.red()))
                return
            if result == number:
                prize = amount * 5
                await self.update_balance(ctx.author.id, ctx.guild.id, prize)
                embed = make_embed(
                    title=f"🎲 ダイス — 大当たり！ {dice_emojis[result]}",
                    description=f"予想: **{number}** → 結果: **{result}**\n**+{format_number(prize)} Kapi Coin** (5倍) 獲得！",
                    color=discord.Color.gold(),
                    footer=f"残高: {format_number(balance + prize)} Kapi Coin",
                )
            else:
                await self.update_balance(ctx.author.id, ctx.guild.id, -amount)
                embed = make_embed(
                    title=f"🎲 ダイス — はずれ {dice_emojis[result]}",
                    description=f"予想: **{number}** → 結果: **{result}**\n**-{format_number(amount)} Kapi Coin**",
                    color=discord.Color.red(),
                    footer=f"残高: {format_number(balance - amount)} Kapi Coin",
                )
        else:
            # 奇数/偶数で倍 (1.9倍)
            user_roll = random.randint(1, 6)
            if user_roll > result:
                prize = int(amount * 1.9)
                await self.update_balance(ctx.author.id, ctx.guild.id, prize)
                embed = make_embed(
                    title=f"🎲 ダイス対決 — 勝利！",
                    description=f"あなた: {dice_emojis[user_roll]} **{user_roll}** vs Bot: {dice_emojis[result]} **{result}**\n**+{format_number(prize)} Kapi Coin** 獲得！",
                    color=discord.Color.green(),
                    footer=f"残高: {format_number(balance + prize)} Kapi Coin",
                )
            elif user_roll == result:
                embed = make_embed(
                    title=f"🎲 ダイス対決 — 引き分け",
                    description=f"あなた: {dice_emojis[user_roll]} **{user_roll}** vs Bot: {dice_emojis[result]} **{result}**\n賭け金は返還されます。",
                    color=discord.Color.blue(),
                    footer=f"残高: {format_number(balance)} Kapi Coin",
                )
            else:
                await self.update_balance(ctx.author.id, ctx.guild.id, -amount)
                embed = make_embed(
                    title=f"🎲 ダイス対決 — 敗北...",
                    description=f"あなた: {dice_emojis[user_roll]} **{user_roll}** vs Bot: {dice_emojis[result]} **{result}**\n**-{format_number(amount)} Kapi Coin**",
                    color=discord.Color.red(),
                    footer=f"残高: {format_number(balance - amount)} Kapi Coin",
                )
        await ctx.send(embed=embed)

    # ─── スロット ────────────────────────────────────────────────

    @commands.command(name="slots", aliases=["slot", "スロット"])
    async def slots(self, ctx, bet: str):
        """スロットマシンでKapi Coinを賭けます\n使い方: kapi slots <賭け金>"""
        balance = await self.get_balance(ctx.author.id, ctx.guild.id)
        amount = self.parse_bet(bet, balance)

        if amount is None:
            await ctx.send(embed=make_embed(description="賭け金を正しく指定してください。", color=discord.Color.red()))
            return
        if amount <= 0 or amount > balance:
            await ctx.send(embed=make_embed(description=f"賭け金が無効です。残高: **{format_number(balance)} Kapi Coin**", color=discord.Color.red()))
            return

        symbols = ["🍒", "🍋", "🍊", "🍇", "⭐", "💎", "7️⃣"]
        weights = [30, 25, 20, 15, 6, 3, 1]
        reels = random.choices(symbols, weights=weights, k=3)

        if reels[0] == reels[1] == reels[2]:
            sym = reels[0]
            multipliers = {
                "🍒": 2, "🍋": 3, "🍊": 4, "🍇": 5,
                "⭐": 10, "💎": 20, "7️⃣": 50
            }
            mult = multipliers.get(sym, 2)
            prize = amount * mult
            await self.update_balance(ctx.author.id, ctx.guild.id, prize)
            embed = make_embed(
                title="🎰 スロット — ジャックポット！！",
                description=f"[ {' | '.join(reels)} ]\n\n**{mult}倍！ +{format_number(prize)} Kapi Coin** 獲得！",
                color=discord.Color.gold(),
                footer=f"残高: {format_number(balance + prize)} Kapi Coin",
            )
        elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
            prize = int(amount * 1.5)
            await self.update_balance(ctx.author.id, ctx.guild.id, prize)
            embed = make_embed(
                title="🎰 スロット — 小当たり！",
                description=f"[ {' | '.join(reels)} ]\n\n2つ揃い！ **+{format_number(prize)} Kapi Coin** 獲得！",
                color=discord.Color.green(),
                footer=f"残高: {format_number(balance + prize)} Kapi Coin",
            )
        else:
            await self.update_balance(ctx.author.id, ctx.guild.id, -amount)
            embed = make_embed(
                title="🎰 スロット — はずれ",
                description=f"[ {' | '.join(reels)} ]\n\n**-{format_number(amount)} Kapi Coin**",
                color=discord.Color.red(),
                footer=f"残高: {format_number(balance - amount)} Kapi Coin",
            )
        await ctx.send(embed=embed)

    # ─── ブラックジャック ─────────────────────────────────────────

    def card_value(self, card: str) -> int:
        rank = card[:-1]
        if rank in ("J", "Q", "K"):
            return 10
        if rank == "A":
            return 11
        return int(rank)

    def hand_value(self, hand: list) -> int:
        total = sum(self.card_value(c) for c in hand)
        aces = sum(1 for c in hand if c[:-1] == "A")
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def new_deck(self) -> list:
        suits = ["♠", "♥", "♦", "♣"]
        ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        deck = [f"{r}{s}" for s in suits for r in ranks]
        random.shuffle(deck)
        return deck

    def format_hand(self, hand: list, hide_second: bool = False) -> str:
        if hide_second:
            return f"`{hand[0]}` `??`"
        return " ".join(f"`{c}`" for c in hand)

    @commands.command(name="blackjack", aliases=["bj", "ブラックジャック"])
    async def blackjack(self, ctx, bet: str):
        """ブラックジャックでKapi Coinを賭けます\n使い方: kapi blackjack <賭け金>"""
        balance = await self.get_balance(ctx.author.id, ctx.guild.id)
        amount = self.parse_bet(bet, balance)

        if amount is None:
            await ctx.send(embed=make_embed(description="賭け金を正しく指定してください。", color=discord.Color.red()))
            return
        if amount <= 0 or amount > balance:
            await ctx.send(embed=make_embed(description=f"賭け金が無効です。残高: **{format_number(balance)} Kapi Coin**", color=discord.Color.red()))
            return

        deck = self.new_deck()
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        async def show_table(title: str, reveal_dealer: bool = False, color=discord.Color.blurple()):
            pv = self.hand_value(player)
            dv = self.hand_value(dealer)
            embed = make_embed(title=f"🃏 ブラックジャック — {title}", color=color)
            embed.add_field(
                name=f"あなたの手札 ({pv})",
                value=self.format_hand(player),
                inline=False,
            )
            embed.add_field(
                name=f"ディーラーの手札 ({dv if reveal_dealer else '?'})",
                value=self.format_hand(dealer, hide_second=not reveal_dealer),
                inline=False,
            )
            embed.set_footer(text=f"賭け金: {format_number(amount)} Kapi Coin | 残高: {format_number(balance)} Kapi Coin")
            return embed

        # ブラックジャックチェック
        if self.hand_value(player) == 21:
            prize = int(amount * 1.5)
            await self.update_balance(ctx.author.id, ctx.guild.id, prize)
            embed = await show_table("ブラックジャック！🎉", reveal_dealer=True, color=discord.Color.gold())
            embed.description = f"ブラックジャック！ **+{format_number(prize)} Kapi Coin** (1.5倍) 獲得！"
            await ctx.send(embed=embed)
            return

        embed = await show_table("ゲーム開始")
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("👊")  # Hit
        await msg.add_reaction("🛑")  # Stand

        def check(reaction, user):
            return (
                user == ctx.author
                and str(reaction.emoji) in ["👊", "🛑"]
                and reaction.message.id == msg.id
            )

        import asyncio
        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            except asyncio.TimeoutError:
                await msg.edit(embed=await show_table("タイムアウト — スタンド扱い", reveal_dealer=True))
                break

            if str(reaction.emoji) == "👊":  # Hit
                player.append(deck.pop())
                pv = self.hand_value(player)
                if pv > 21:
                    await self.update_balance(ctx.author.id, ctx.guild.id, -amount)
                    embed = await show_table("バスト！", reveal_dealer=True, color=discord.Color.red())
                    embed.description = f"バスト！ **-{format_number(amount)} Kapi Coin**"
                    await msg.edit(embed=embed)
                    return
                elif pv == 21:
                    embed = await show_table("21！スタンドします", reveal_dealer=False)
                    await msg.edit(embed=embed)
                    break
                else:
                    embed = await show_table("ゲーム中")
                    await msg.edit(embed=embed)
                try:
                    await msg.remove_reaction(reaction, user)
                except Exception:
                    pass
            else:  # Stand
                break

        # ディーラーのターン
        while self.hand_value(dealer) < 17:
            dealer.append(deck.pop())

        pv = self.hand_value(player)
        dv = self.hand_value(dealer)

        if dv > 21 or pv > dv:
            await self.update_balance(ctx.author.id, ctx.guild.id, amount)
            embed = await show_table("勝利！🎉", reveal_dealer=True, color=discord.Color.green())
            embed.description = f"あなた: {pv} vs ディーラー: {dv}\n**+{format_number(amount)} Kapi Coin** 獲得！"
        elif pv == dv:
            embed = await show_table("引き分け", reveal_dealer=True, color=discord.Color.blue())
            embed.description = f"あなた: {pv} vs ディーラー: {dv}\n賭け金は返還されます。"
        else:
            await self.update_balance(ctx.author.id, ctx.guild.id, -amount)
            embed = await show_table("敗北...", reveal_dealer=True, color=discord.Color.red())
            embed.description = f"あなた: {pv} vs ディーラー: {dv}\n**-{format_number(amount)} Kapi Coin**"

        await msg.edit(embed=embed)

    # ─── ルーレット ────────────────────────────────────────────

    @commands.command(name="roulette", aliases=["ルーレット"])
    async def roulette(self, ctx, bet: str, *, choice: str):
        """ルーレットでKapi Coinを賭けます\n選択肢: 赤/黒, 奇数/偶数, 0-36の数字\n例: kapi roulette 100 赤"""
        balance = await self.get_balance(ctx.author.id, ctx.guild.id)
        amount = self.parse_bet(bet, balance)

        if amount is None:
            await ctx.send(embed=make_embed(description="賭け金を正しく指定してください。", color=discord.Color.red()))
            return
        if amount <= 0 or amount > balance:
            await ctx.send(embed=make_embed(description=f"賭け金が無効です。残高: **{format_number(balance)} Kapi Coin**", color=discord.Color.red()))
            return

        result = random.randint(0, 36)
        red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        is_red = result in red_numbers
        color_str = "🔴 赤" if is_red else ("⚫ 黒" if result != 0 else "🟢 緑(0)")

        choice = choice.lower().strip()
        win = False
        mult = 1

        if choice in ("赤", "red", "r"):
            win = is_red and result != 0
            mult = 2
        elif choice in ("黒", "black", "b"):
            win = not is_red and result != 0
            mult = 2
        elif choice in ("奇数", "odd"):
            win = result % 2 == 1
            mult = 2
        elif choice in ("偶数", "even"):
            win = result % 2 == 0 and result != 0
            mult = 2
        else:
            try:
                num = int(choice)
                if 0 <= num <= 36:
                    win = result == num
                    mult = 35
                else:
                    await ctx.send(embed=make_embed(description="0〜36の数字、または 赤/黒/奇数/偶数 を指定してください。", color=discord.Color.red()))
                    return
            except ValueError:
                await ctx.send(embed=make_embed(description="0〜36の数字、または 赤/黒/奇数/偶数 を指定してください。", color=discord.Color.red()))
                return

        if win:
            prize = amount * mult
            await self.update_balance(ctx.author.id, ctx.guild.id, prize)
            embed = make_embed(
                title="🎡 ルーレット — 当たり！",
                description=f"結果: **{result}** ({color_str})\n\n**+{format_number(prize)} Kapi Coin** ({mult}倍) 獲得！",
                color=discord.Color.green(),
                footer=f"残高: {format_number(balance + prize)} Kapi Coin",
            )
        else:
            await self.update_balance(ctx.author.id, ctx.guild.id, -amount)
            embed = make_embed(
                title="🎡 ルーレット — はずれ",
                description=f"結果: **{result}** ({color_str})\n\n**-{format_number(amount)} Kapi Coin**",
                color=discord.Color.red(),
                footer=f"残高: {format_number(balance - amount)} Kapi Coin",
            )
        await ctx.send(embed=embed)


    # ─── 箱選びゲーム ────────────────────────────────────────────

    @commands.command(name="box", aliases=["箱", "はこ"])
    async def box(self, ctx, bet: str, number: int):
        """5つの箱から1つを選ぶゲーム。1つだけハズレ！\n使い方: kapi box <賭け金> <1-5>\n当たりなら2倍、ハズレなら-3倍！"""
        balance = await self.get_balance(ctx.author.id, ctx.guild.id)
        amount = self.parse_bet(bet, balance)

        if amount is None:
            await ctx.send(embed=make_embed(description="賭け金を正しく指定してください。", color=discord.Color.red()))
            return
        if amount <= 0 or amount > balance:
            await ctx.send(embed=make_embed(description=f"賭け金が無効です。残高: **{format_number(balance)} Kapi Coin**", color=discord.Color.red()))
            return
        if number < 1 or number > 5:
            await ctx.send(embed=make_embed(description="1〜5の番号を指定してください。", color=discord.Color.red()))
            return

        hazure = random.randint(1, 5)
        boxes = []
        for i in range(1, 6):
            if i == number:
                boxes.append(f"**[{i}]**" if i != hazure else f"💣**[{i}]**")
            elif i == hazure:
                boxes.append(f"💣{i}")
            else:
                boxes.append(f"✅{i}")

        reveal = " | ".join(boxes)

        if number == hazure:
            penalty = amount * 3
            actual_penalty = min(penalty, balance)
            await self.update_balance(ctx.author.id, ctx.guild.id, -actual_penalty)
            embed = make_embed(
                title="📦 箱選び — 💣 ハズレ！！！",
                description=f"{reveal}\n\n爆発！ **-{format_number(actual_penalty)} Kapi Coin** (3倍ペナルティ) 💀",
                color=discord.Color.dark_red(),
                footer=f"残高: {format_number(balance - actual_penalty)} Kapi Coin",
            )
        else:
            prize = amount * 2
            await self.update_balance(ctx.author.id, ctx.guild.id, prize)
            embed = make_embed(
                title="📦 箱選び — ✅ 当たり！",
                description=f"{reveal}\n\n**+{format_number(prize)} Kapi Coin** (2倍) 獲得！",
                color=discord.Color.green(),
                footer=f"残高: {format_number(balance + prize)} Kapi Coin",
            )
        await ctx.send(embed=embed)

    # ─── ロシアンルーレット ──────────────────────────────────────

    @commands.command(name="russianroulette", aliases=["rr", "ロシアンルーレット"])
    async def russianroulette(self, ctx, bet: str, chambers: int = 6):
        """ロシアンルーレット！弾が入ってなければ大勝利\n使い方: kapi rr <賭け金> [シリンダー数 2-12]\nデフォルト6発中1発。当たり確率低いほど倍率UP！"""
        balance = await self.get_balance(ctx.author.id, ctx.guild.id)
        amount = self.parse_bet(bet, balance)

        if amount is None:
            await ctx.send(embed=make_embed(description="賭け金を正しく指定してください。", color=discord.Color.red()))
            return
        if amount <= 0 or amount > balance:
            await ctx.send(embed=make_embed(description=f"賭け金が無効です。残高: **{format_number(balance)} Kapi Coin**", color=discord.Color.red()))
            return
        if chambers < 2 or chambers > 12:
            await ctx.send(embed=make_embed(description="シリンダー数は2〜12で指定してください。", color=discord.Color.red()))
            return

        bullet_pos = random.randint(1, chambers)
        fired = random.randint(1, chambers)
        hit = fired == bullet_pos

        # 倍率: シリンダー数が多いほど高倍率
        multiplier = round(chambers / (chambers - 1), 2)

        if hit:
            penalty = min(amount * 5, balance)
            await self.update_balance(ctx.author.id, ctx.guild.id, -penalty)
            embed = make_embed(
                title="🔫 ロシアンルーレット — 💥 バン！！",
                description=f"シリンダー {chambers} 発中、引き金を引いたら...\n\n**💥 当たった！！** **-{format_number(penalty)} Kapi Coin** 💀",
                color=discord.Color.dark_red(),
                footer=f"残高: {format_number(balance - penalty)} Kapi Coin | 確率: 1/{chambers}",
            )
        else:
            prize = int(amount * multiplier)
            await self.update_balance(ctx.author.id, ctx.guild.id, prize)
            embed = make_embed(
                title="🔫 ロシアンルーレット — カチッ",
                description=f"シリンダー {chambers} 発中、引き金を引いたら...\n\n**空砲！ 生き残った！** **+{format_number(prize)} Kapi Coin** ({multiplier}倍) 🎉",
                color=discord.Color.green(),
                footer=f"残高: {format_number(balance + prize)} Kapi Coin | 確率: {chambers-1}/{chambers}",
            )
        await ctx.send(embed=embed)

    # ─── ハイローカード ──────────────────────────────────────────

    @commands.command(name="highlow", aliases=["hl", "ハイロー"])
    async def highlow(self, ctx, bet: str):
        """カードを引いて次が高い(High)か低い(Low)かを当てる\n使い方: kapi highlow <賭け金>\n👆 High（高い）か 👇 Low（低い）をリアクションで選択"""
        balance = await self.get_balance(ctx.author.id, ctx.guild.id)
        amount = self.parse_bet(bet, balance)

        if amount is None:
            await ctx.send(embed=make_embed(description="賭け金を正しく指定してください。", color=discord.Color.red()))
            return
        if amount <= 0 or amount > balance:
            await ctx.send(embed=make_embed(description=f"賭け金が無効です。残高: **{format_number(balance)} Kapi Coin**", color=discord.Color.red()))
            return

        suits = ["♠", "♥", "♦", "♣"]
        ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        rank_values = {r: i+1 for i, r in enumerate(ranks)}

        current_card = f"{random.choice(ranks)}{random.choice(suits)}"
        current_val = rank_values[current_card[:-1]]

        embed = make_embed(
            title="🃏 ハイロー",
            description=f"現在のカード: **{current_card}** (値: {current_val})\n\n次のカードは高い？低い？\n👆 High (高い) | 👇 Low (低い)",
            color=discord.Color.blurple(),
            footer=f"賭け金: {format_number(amount)} Kapi Coin",
        )
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("👆")
        await msg.add_reaction("👇")

        def check(reaction, user):
            return (
                user == ctx.author
                and str(reaction.emoji) in ["👆", "👇"]
                and reaction.message.id == msg.id
            )

        import asyncio
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=20.0, check=check)
        except asyncio.TimeoutError:
            await msg.edit(embed=make_embed(title="🃏 ハイロー — タイムアウト", description="時間切れです。", color=discord.Color.red()))
            return

        next_card = f"{random.choice(ranks)}{random.choice(suits)}"
        next_val = rank_values[next_card[:-1]]
        choice = "high" if str(reaction.emoji) == "👆" else "low"

        if next_val == current_val:
            embed = make_embed(
                title="🃏 ハイロー — 引き分け",
                description=f"現在: **{current_card}** ({current_val}) → 次: **{next_card}** ({next_val})\n同じ値！賭け金返還。",
                color=discord.Color.blue(),
                footer=f"残高: {format_number(balance)} Kapi Coin",
            )
        elif (choice == "high" and next_val > current_val) or (choice == "low" and next_val < current_val):
            prize = int(amount * 1.9)
            await self.update_balance(ctx.author.id, ctx.guild.id, prize)
            embed = make_embed(
                title="🃏 ハイロー — 正解！",
                description=f"現在: **{current_card}** ({current_val}) → 次: **{next_card}** ({next_val})\n**+{format_number(prize)} Kapi Coin** 獲得！",
                color=discord.Color.green(),
                footer=f"残高: {format_number(balance + prize)} Kapi Coin",
            )
        else:
            await self.update_balance(ctx.author.id, ctx.guild.id, -amount)
            embed = make_embed(
                title="🃏 ハイロー — ハズレ！",
                description=f"現在: **{current_card}** ({current_val}) → 次: **{next_card}** ({next_val})\n**-{format_number(amount)} Kapi Coin**",
                color=discord.Color.red(),
                footer=f"残高: {format_number(balance - amount)} Kapi Coin",
            )
        await msg.edit(embed=embed)


async def setup(bot):
    await bot.add_cog(Gambling(bot))
