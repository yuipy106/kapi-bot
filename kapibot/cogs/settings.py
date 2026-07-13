import discord
from discord.ext import commands
import aiosqlite
from utils.database import DB_PATH
from utils.helpers import make_embed


class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="settings", aliases=["設定", "config"])
    @commands.has_permissions(administrator=True)
    async def settings(self, ctx):
        """現在のサーバー設定を表示します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                """SELECT log_channel_id, welcome_channel_id, leave_channel_id,
                          level_up_channel_id, xp_rate, xp_cooldown
                   FROM guild_settings WHERE guild_id=?""",
                (ctx.guild.id,),
            ) as cur:
                row = await cur.fetchone()

        def channel_str(cid):
            if not cid:
                return "未設定"
            ch = ctx.guild.get_channel(cid)
            return ch.mention if ch else f"<#{cid}> (削除済み)"

        embed = make_embed(
            title=f"⚙️ {ctx.guild.name} の設定",
            color=discord.Color.blurple(),
            thumbnail=ctx.guild.icon.url if ctx.guild.icon else None,
        )

        if row:
            log_ch, welcome_ch, leave_ch, lvlup_ch, xp_rate, xp_cd = row
            embed.add_field(name="📋 ログチャンネル", value=channel_str(log_ch), inline=True)
            embed.add_field(name="👋 歓迎チャンネル", value=channel_str(welcome_ch), inline=True)
            embed.add_field(name="🚪 退出チャンネル", value=channel_str(leave_ch), inline=True)
            embed.add_field(name="🆙 レベルアップチャンネル", value=channel_str(lvlup_ch), inline=True)
            embed.add_field(name="✨ XPレート", value=f"{xp_rate or 10}〜{(xp_rate or 10) * 2}", inline=True)
            embed.add_field(name="⏱️ XPクールダウン", value=f"{xp_cd or 60}秒", inline=True)
        else:
            embed.description = "設定がまだありません。各コマンドで設定してください。"

        embed.add_field(
            name="📖 設定コマンド一覧",
            value=(
                "`kapi setlog #ch` — ログチャンネル\n"
                "`kapi setwelcome #ch [メッセージ]` — 歓迎設定\n"
                "`kapi setleave #ch [メッセージ]` — 退出設定\n"
                "`kapi setlevelupchannel #ch` — レベルアップチャンネル\n"
                "`kapi setxprate <数値>` — XPレート設定\n"
                "`kapi setxpcooldown <秒>` — XPクールダウン設定\n"
                "`kapi ticketsetup` — チケット設定"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.command(name="setlevelupchannel", aliases=["レベルアップチャンネル設定"])
    @commands.has_permissions(administrator=True)
    async def setlevelupchannel(self, ctx, channel: discord.TextChannel):
        """レベルアップ通知チャンネルを設定します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO guild_settings (guild_id, level_up_channel_id)
                   VALUES (?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET level_up_channel_id=?""",
                (ctx.guild.id, channel.id, channel.id),
            )
            await db.commit()
        await ctx.send(
            embed=make_embed(
                description=f"レベルアップ通知チャンネルを {channel.mention} に設定しました。",
                color=discord.Color.green(),
            )
        )

    @commands.command(name="setxprate", aliases=["XPレート設定"])
    @commands.has_permissions(administrator=True)
    async def setxprate(self, ctx, rate: int):
        """XPの獲得量を設定します（管理者専用）"""
        if rate < 1 or rate > 100:
            await ctx.send(embed=make_embed(description="XPレートは1〜100の間で指定してください。", color=discord.Color.red()))
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO guild_settings (guild_id, xp_rate)
                   VALUES (?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET xp_rate=?""",
                (ctx.guild.id, rate, rate),
            )
            await db.commit()
        await ctx.send(
            embed=make_embed(
                description=f"XPレートを **{rate}〜{rate*2}** に設定しました。",
                color=discord.Color.green(),
            )
        )

    @commands.command(name="setxpcooldown", aliases=["XPクールダウン設定"])
    @commands.has_permissions(administrator=True)
    async def setxpcooldown(self, ctx, seconds: int):
        """XP獲得のクールダウンを設定します（管理者専用）"""
        if seconds < 0 or seconds > 3600:
            await ctx.send(embed=make_embed(description="クールダウンは0〜3600秒の間で指定してください。", color=discord.Color.red()))
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO guild_settings (guild_id, xp_cooldown)
                   VALUES (?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET xp_cooldown=?""",
                (ctx.guild.id, seconds, seconds),
            )
            await db.commit()
        await ctx.send(
            embed=make_embed(
                description=f"XPクールダウンを **{seconds}秒** に設定しました。",
                color=discord.Color.green(),
            )
        )

    @commands.command(name="help", aliases=["ヘルプ"])
    async def help(self, ctx, *, category: str = None):
        """KapiBotのコマンド一覧を表示します"""
        categories = {
            "economy": {
                "title": "💰 経済システム",
                "commands": [
                    ("balance [@メンバー]", "Kapi Coinの残高を確認"),
                    ("daily", "毎日Kapi Coinをもらう"),
                    ("work", "お仕事してKapi Coinを稼ぐ（1時間CD）"),
                    ("pay @メンバー <金額>", "Kapi Coinを送金"),
                    ("shop", "ショップを表示"),
                    ("buy <ID>", "アイテムを購入"),
                    ("sell <ID> [個数]", "アイテムを売却"),
                    ("inventory [@メンバー]", "インベントリを確認"),
                    ("leaderboard", "Kapi Coinランキング"),
                ],
            },
            "levels": {
                "title": "📊 レベルシステム",
                "commands": [
                    ("rank [@メンバー]", "ランクとXPを確認"),
                    ("levelboard", "レベルランキング"),
                    ("setlevelrole <レベル> @ロール", "レベルロールを設定【管理者】"),
                    ("setlevelupchannel #チャンネル", "レベルアップ通知チャンネル設定【管理者】"),
                    ("setxprate <数値>", "XPレート設定【管理者】"),
                ],
            },
            "gacha": {
                "title": "🎰 ガチャシステム",
                "commands": [
                    ("gacha", f"ガチャを1回引く（100 Kapi Coin）"),
                    ("gacha10", "10連ガチャ（900 Kapi Coin）"),
                    ("gachalist", "ガチャアイテム一覧"),
                    ("gachainv [@メンバー]", "ガチャコレクションを確認"),
                    ("addgacha <レアリティ> <重み> [@ロール] <名前>", "ガチャアイテム追加【管理者】"),
                ],
            },
            "roles": {
                "title": "🎭 ロール選択",
                "commands": [
                    ("createrolepanel [タイトル] [説明]", "ロールパネル作成【管理者】"),
                    ("addrolepanel <ID> @ロール [ラベル] [絵文字]", "ロール追加【管理者】"),
                    ("publishrolepanel <ID>", "ロールパネル公開【管理者】"),
                    ("resetroleselect @メンバー", "ロール選択リセット【管理者】"),
                ],
            },
            "tickets": {
                "title": "🎫 チケットシステム",
                "commands": [
                    ("ticketpanel [説明]", "チケットパネル設置【管理者】"),
                    ("ticketsetup [カテゴリ] [ログch] [サポートロール]", "チケット設定【管理者】"),
                    ("closeticket", "チケットを閉じる【スタッフ】"),
                ],
            },
            "mod": {
                "title": "🛡️ モデレーション",
                "commands": [
                    ("ban @メンバー [理由]", "BANする"),
                    ("unban <ユーザーID> [理由]", "BAN解除"),
                    ("kick @メンバー [理由]", "KICKする"),
                    ("timeout @メンバー <時間> <単位> [理由]", "タイムアウト（s/m/h/d）"),
                    ("untimeout @メンバー", "タイムアウト解除"),
                    ("purge <件数>", "メッセージ一括削除（最大100）"),
                    ("warn @メンバー [理由]", "警告を発行"),
                    ("warnings [@メンバー]", "警告一覧"),
                    ("clearwarn <ID>", "警告を削除"),
                ],
            },
            "settings": {
                "title": "⚙️ サーバー設定",
                "commands": [
                    ("settings", "現在の設定を表示【管理者】"),
                    ("setlog #チャンネル", "ログチャンネル設定【管理者】"),
                    ("setwelcome #チャンネル [メッセージ]", "歓迎設定【管理者】"),
                    ("setleave #チャンネル [メッセージ]", "退出設定【管理者】"),
                    ("testwelcome", "歓迎メッセージテスト【管理者】"),
                    ("testleave", "退出メッセージテスト【管理者】"),
                ],
            },
        }

        if category and category.lower() in categories:
            cat = categories[category.lower()]
            embed = make_embed(title=cat["title"], color=discord.Color.blurple())
            for cmd, desc in cat["commands"]:
                embed.add_field(name=f"`kapi {cmd}`", value=desc, inline=False)
            await ctx.send(embed=embed)
            return

        embed = make_embed(
            title="🤖 KapiBot ヘルプ",
            description="各カテゴリの詳細は `kapi help <カテゴリ>` で確認できます。",
            color=discord.Color.blurple(),
            thumbnail=self.bot.user.display_avatar.url if self.bot.user else None,
        )
        for key, cat in categories.items():
            cmds = [f"`{c}`" for c, _ in cat["commands"][:3]]
            embed.add_field(
                name=cat["title"],
                value=f"詳細: `kapi help {key}`\n" + " / ".join(cmds) + ("..." if len(cat["commands"]) > 3 else ""),
                inline=False,
            )
        embed.set_footer(text="プレフィックス: kapi  |  開発: KapiBot")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Settings(bot))
