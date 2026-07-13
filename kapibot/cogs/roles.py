import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime, timezone
from utils.database import DB_PATH
from utils.helpers import make_embed


class RoleSelect(discord.ui.Select):
    def __init__(self, roles: list, panel_id: int):
        self.panel_id = panel_id
        options = [
            discord.SelectOption(
                label=label or role.name,
                value=str(role_id),
                emoji=emoji,
            )
            for role_id, label, emoji, role in roles
            if role is not None
        ]
        super().__init__(
            placeholder="ロールを選択してください",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        guild_id = interaction.guild.id

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT selected_at FROM role_selections WHERE user_id=? AND guild_id=?",
                (user_id, guild_id),
            ) as cur:
                row = await cur.fetchone()

        if row:
            await interaction.response.send_message(
                embed=make_embed(
                    description="ロールはすでに選択済みです。変更する場合は管理者にリセットを依頼してください。",
                    color=discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message("ロールが見つかりませんでした。", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(role, reason="ロール選択パネルから選択")
        except discord.Forbidden:
            await interaction.response.send_message("ロールを付与する権限がありません。", ephemeral=True)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO role_selections (user_id, guild_id, selected_at) VALUES (?, ?, ?)",
                (user_id, guild_id, datetime.utcnow().isoformat()),
            )
            await db.commit()

        await interaction.response.send_message(
            embed=make_embed(
                description=f"✅ {role.mention} を選択しました！この選択は変更できません。",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )


class RoleView(discord.ui.View):
    def __init__(self, roles: list, panel_id: int):
        super().__init__(timeout=None)
        self.add_item(RoleSelect(roles, panel_id))


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await self.restore_views()

    async def restore_views(self):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT id FROM role_panels") as cur:
                panels = await cur.fetchall()

        for (panel_id,) in panels:
            await self.get_view_for_panel(panel_id)

    async def get_view_for_panel(self, panel_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT role_id, label, emoji FROM role_panel_roles WHERE panel_id=?",
                (panel_id,),
            ) as cur:
                role_rows = await cur.fetchall()
            async with db.execute(
                "SELECT guild_id FROM role_panels WHERE id=?",
                (panel_id,),
            ) as cur:
                panel_row = await cur.fetchone()

        if not panel_row:
            return None

        guild = self.bot.get_guild(panel_row[0])
        if not guild:
            return None

        roles = []
        for role_id, label, emoji in role_rows:
            role = guild.get_role(role_id)
            roles.append((role_id, label, emoji, role))

        return RoleView(roles, panel_id)

    @commands.command(name="createrolepanel", aliases=["ロールパネル作成"])
    @commands.has_permissions(administrator=True)
    async def createrolepanel(self, ctx, title: str = "ロール選択", *, description: str = "ロールを1つ選択してください。選択後は変更できません。"):
        """ロール選択パネルを作成します（管理者専用）\n次に kapi addrolepanel <パネルID> @ロール でロールを追加"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO role_panels (guild_id, channel_id, title, description) VALUES (?, ?, ?, ?)",
                (ctx.guild.id, ctx.channel.id, title, description),
            )
            panel_id = cursor.lastrowid
            await db.commit()

        embed = make_embed(
            title="✅ ロールパネルを作成しました",
            description=f"パネルID: **{panel_id}**\n\n`kapi addrolepanel {panel_id} @ロール [ラベル] [絵文字]` でロールを追加後、\n`kapi publishrolepanel {panel_id}` で公開してください。",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="addrolepanel", aliases=["ロールパネル追加"])
    @commands.has_permissions(administrator=True)
    async def addrolepanel(self, ctx, panel_id: int, role: discord.Role, label: str = None, emoji: str = None):
        """ロールパネルにロールを追加します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id FROM role_panels WHERE id=? AND guild_id=?",
                (panel_id, ctx.guild.id),
            ) as cur:
                row = await cur.fetchone()

        if not row:
            await ctx.send(embed=make_embed(description="そのパネルIDは存在しません。", color=discord.Color.red()))
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO role_panel_roles (panel_id, role_id, label, emoji) VALUES (?, ?, ?, ?)",
                (panel_id, role.id, label or role.name, emoji),
            )
            await db.commit()

        await ctx.send(
            embed=make_embed(
                description=f"{role.mention} をパネル #{panel_id} に追加しました。",
                color=discord.Color.green(),
            )
        )

    @commands.command(name="publishrolepanel", aliases=["ロールパネル公開"])
    @commands.has_permissions(administrator=True)
    async def publishrolepanel(self, ctx, panel_id: int):
        """ロールパネルを公開します（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_id, title, description FROM role_panels WHERE id=? AND guild_id=?",
                (panel_id, ctx.guild.id),
            ) as cur:
                row = await cur.fetchone()

        if not row:
            await ctx.send(embed=make_embed(description="そのパネルIDは存在しません。", color=discord.Color.red()))
            return

        channel_id, title, description = row
        channel = ctx.guild.get_channel(channel_id) or ctx.channel
        view = await self.get_view_for_panel(panel_id)

        if not view:
            await ctx.send(embed=make_embed(description="ロールが追加されていません。", color=discord.Color.red()))
            return

        embed = make_embed(
            title=f"🎭 {title}",
            description=description,
            color=discord.Color.blurple(),
        )
        msg = await channel.send(embed=embed, view=view)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE role_panels SET message_id=? WHERE id=?",
                (msg.id, panel_id),
            )
            await db.commit()

        if channel != ctx.channel:
            await ctx.send(
                embed=make_embed(
                    description=f"ロールパネルを {channel.mention} に公開しました。",
                    color=discord.Color.green(),
                )
            )

    @commands.command(name="resetroleselect", aliases=["ロール選択リセット"])
    @commands.has_permissions(administrator=True)
    async def resetroleselect(self, ctx, member: discord.Member):
        """メンバーのロール選択をリセットします（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM role_selections WHERE user_id=? AND guild_id=?",
                (member.id, ctx.guild.id),
            )
            await db.commit()
        embed = make_embed(
            description=f"{member.mention} のロール選択をリセットしました。",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    # ─── 一生に一度ロール (Once-Only Roles) ──────────────────────

    @commands.command(name="addoncerole", aliases=["一度ロール追加"])
    @commands.has_permissions(administrator=True)
    async def addoncerole(self, ctx, role: discord.Role, *, description: str = None):
        """一生に一度しか取得できないロールを登録します（管理者専用）\n使い方: kapi addoncerole @ロール [説明]"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO once_roles (guild_id, role_id, description) VALUES (?, ?, ?)",
                (ctx.guild.id, role.id, description),
            )
            await db.commit()
        await ctx.send(embed=make_embed(
            title="🔒 一度限りロール登録",
            description=f"✅ {role.mention} を「一生に一度だけ」取得できるロールに登録しました。\n\nユーザーは `kapi claim {role.name}` で取得できます。",
            color=discord.Color.green(),
        ))

    @commands.command(name="removeoncerole", aliases=["一度ロール削除"])
    @commands.has_permissions(administrator=True)
    async def removeoncerole(self, ctx, role: discord.Role):
        """一度限りロールの登録を解除します（管理者専用）\n使い方: kapi removeoncerole @ロール"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM once_roles WHERE guild_id=? AND role_id=?",
                (ctx.guild.id, role.id),
            )
            await db.commit()
        await ctx.send(embed=make_embed(
            description=f"🗑️ {role.mention} を一度限りロールから解除しました。",
            color=discord.Color.orange(),
        ))

    @commands.command(name="onceroles", aliases=["一度ロール一覧"])
    async def onceroles(self, ctx):
        """一生に一度だけ取得できるロール一覧を表示します\n使い方: kapi onceroles"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT role_id, description FROM once_roles WHERE guild_id=?",
                (ctx.guild.id,),
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await ctx.send(embed=make_embed(description="一度限りロールが登録されていません。", color=discord.Color.orange()))
            return

        lines = []
        for role_id, desc in rows:
            role = ctx.guild.get_role(role_id)
            if role:
                line = f"🔒 {role.mention}"
                if desc:
                    line += f" — {desc}"
                lines.append(line)

        embed = make_embed(
            title="🔒 一生に一度のロール一覧",
            description="\n".join(lines) if lines else "有効なロールがありません。",
            color=discord.Color.purple(),
            footer="`kapi claim @ロール` で取得（一度きり！）",
        )
        await ctx.send(embed=embed)

    @commands.command(name="claim", aliases=["クレイム", "取得"])
    async def claim(self, ctx, role: discord.Role):
        """一生に一度だけ取得できるロールを受け取ります\n使い方: kapi claim @ロール\n⚠️ 一度取得したら永遠に再取得不可！"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT 1 FROM once_roles WHERE guild_id=? AND role_id=?",
                (ctx.guild.id, role.id),
            ) as cur:
                is_once = await cur.fetchone()

        if not is_once:
            await ctx.send(embed=make_embed(
                description=f"{role.mention} は一度限りロールではありません。`kapi onceroles` で一覧を確認してください。",
                color=discord.Color.red(),
            ))
            return

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT claimed_at FROM once_role_claims WHERE user_id=? AND guild_id=? AND role_id=?",
                (ctx.author.id, ctx.guild.id, role.id),
            ) as cur:
                already = await cur.fetchone()

        if already:
            claimed_at = already[0][:10]
            await ctx.send(embed=make_embed(
                title="🔒 取得不可",
                description=f"あなたはすでに {role.mention} を取得しています（{claimed_at}）。\nこのロールは**一生に一度**しか取得できません。",
                color=discord.Color.red(),
            ))
            return

        try:
            await ctx.author.add_roles(role, reason="一度限りロールをclaimしました")
        except discord.Forbidden:
            await ctx.send(embed=make_embed(description="ロールを付与する権限がありません。", color=discord.Color.red()))
            return

        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO once_role_claims (user_id, guild_id, role_id, claimed_at) VALUES (?, ?, ?, ?)",
                (ctx.author.id, ctx.guild.id, role.id, now),
            )
            await db.commit()

        await ctx.send(embed=make_embed(
            title="🎊 ロール取得成功！",
            description=f"✅ {ctx.author.mention} が {role.mention} を取得しました！\n\n⚠️ このロールは**一生に一度**しか取得できません。大切にしてください！",
            color=discord.Color.purple(),
            footer=f"取得日時: {now[:10]}",
        ))

    @commands.command(name="resetonceclaim", aliases=["一度ロールリセット"])
    @commands.has_permissions(administrator=True)
    async def resetonceclaim(self, ctx, member: discord.Member, role: discord.Role):
        """メンバーの一度限りロール取得履歴をリセットします（管理者専用）\n使い方: kapi resetonceclaim @メンバー @ロール"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM once_role_claims WHERE user_id=? AND guild_id=? AND role_id=?",
                (member.id, ctx.guild.id, role.id),
            )
            await db.commit()
        await ctx.send(embed=make_embed(
            description=f"✅ {member.mention} の {role.mention} の取得履歴をリセットしました。\n再度 `kapi claim` で取得可能になります。",
            color=discord.Color.green(),
        ))

    @commands.command(name="checkclaims", aliases=["クレイム確認"])
    async def checkclaims(self, ctx, member: discord.Member = None):
        """メンバーが取得した一度限りロールを確認します\n使い方: kapi checkclaims [@メンバー]"""
        target = member or ctx.author
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT role_id, claimed_at FROM once_role_claims WHERE user_id=? AND guild_id=?",
                (target.id, ctx.guild.id),
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await ctx.send(embed=make_embed(
                description=f"{target.mention} はまだ一度限りロールを取得していません。",
                color=discord.Color.orange(),
            ))
            return

        lines = []
        for role_id, claimed_at in rows:
            role = ctx.guild.get_role(role_id)
            name = role.mention if role else f"（削除済みロール: {role_id}）"
            lines.append(f"🔒 {name} — {claimed_at[:10]}")

        embed = make_embed(
            title=f"🔒 {target.display_name} の取得済みロール",
            description="\n".join(lines),
            color=discord.Color.purple(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    # ─── 自己ロール (Self-Assignable Roles) ──────────────────────

    @commands.command(name="addselfrole", aliases=["自己ロール追加"])
    @commands.has_permissions(administrator=True)
    async def addselfrole(self, ctx, role: discord.Role, *, description: str = None):
        """自己付与可能なロールを登録します（管理者専用）\n使い方: kapi addselfrole @ロール [説明]"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO self_roles (guild_id, role_id, description) VALUES (?, ?, ?)",
                (ctx.guild.id, role.id, description),
            )
            await db.commit()
        await ctx.send(embed=make_embed(
            description=f"✅ {role.mention} を自己ロールに登録しました。",
            color=discord.Color.green(),
        ))

    @commands.command(name="removeselfrole", aliases=["自己ロール削除"])
    @commands.has_permissions(administrator=True)
    async def removeselfrole(self, ctx, role: discord.Role):
        """自己付与ロールの登録を解除します（管理者専用）\n使い方: kapi removeselfrole @ロール"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM self_roles WHERE guild_id=? AND role_id=?",
                (ctx.guild.id, role.id),
            )
            await db.commit()
        await ctx.send(embed=make_embed(
            description=f"🗑️ {role.mention} を自己ロールから削除しました。",
            color=discord.Color.orange(),
        ))

    @commands.command(name="selfroles", aliases=["自己ロール一覧", "iam?"])
    async def selfroles(self, ctx):
        """自己付与できるロールの一覧を表示します\n使い方: kapi selfroles"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT role_id, description FROM self_roles WHERE guild_id=?",
                (ctx.guild.id,),
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await ctx.send(embed=make_embed(description="自己付与できるロールがありません。管理者に追加を依頼してください。", color=discord.Color.orange()))
            return

        lines = []
        for role_id, desc in rows:
            role = ctx.guild.get_role(role_id)
            if role:
                line = f"• {role.mention}"
                if desc:
                    line += f" — {desc}"
                lines.append(line)

        embed = make_embed(
            title="🎭 自己付与ロール一覧",
            description="\n".join(lines) if lines else "有効なロールがありません。",
            color=discord.Color.blurple(),
            footer="`kapi iam @ロール` で付与 / `kapi iamnot @ロール` で外す",
        )
        await ctx.send(embed=embed)

    @commands.command(name="iam", aliases=["ロール付与"])
    async def iam(self, ctx, role: discord.Role):
        """自己ロールを自分に付与します\n使い方: kapi iam @ロール"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT 1 FROM self_roles WHERE guild_id=? AND role_id=?",
                (ctx.guild.id, role.id),
            ) as cur:
                row = await cur.fetchone()

        if not row:
            await ctx.send(embed=make_embed(description=f"{role.mention} は自己付与できないロールです。`kapi selfroles` で一覧を確認してください。", color=discord.Color.red()))
            return

        if role in ctx.author.roles:
            await ctx.send(embed=make_embed(description=f"すでに {role.mention} を持っています。", color=discord.Color.orange()))
            return

        try:
            await ctx.author.add_roles(role, reason="自己ロール付与")
            await ctx.send(embed=make_embed(description=f"✅ {role.mention} を付与しました！", color=discord.Color.green()))
        except discord.Forbidden:
            await ctx.send(embed=make_embed(description="ロールを付与する権限がありません。", color=discord.Color.red()))

    @commands.command(name="iamnot", aliases=["ロール外す"])
    async def iamnot(self, ctx, role: discord.Role):
        """自己ロールを自分から外します\n使い方: kapi iamnot @ロール"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT 1 FROM self_roles WHERE guild_id=? AND role_id=?",
                (ctx.guild.id, role.id),
            ) as cur:
                row = await cur.fetchone()

        if not row:
            await ctx.send(embed=make_embed(description=f"{role.mention} は自己付与ロールではないため外せません。", color=discord.Color.red()))
            return

        if role not in ctx.author.roles:
            await ctx.send(embed=make_embed(description=f"{role.mention} を持っていません。", color=discord.Color.orange()))
            return

        try:
            await ctx.author.remove_roles(role, reason="自己ロール解除")
            await ctx.send(embed=make_embed(description=f"✅ {role.mention} を外しました。", color=discord.Color.green()))
        except discord.Forbidden:
            await ctx.send(embed=make_embed(description="ロールを外す権限がありません。", color=discord.Color.red()))

    # ─── ロールショップ (Role Shop) ───────────────────────────────

    @commands.command(name="addroleshop", aliases=["ロールショップ追加"])
    @commands.has_permissions(administrator=True)
    async def addroleshop(self, ctx, role: discord.Role, price: int, *, description: str = None):
        """ロールをショップに追加します（管理者専用）\n使い方: kapi addroleshop @ロール <価格> [説明]"""
        if price <= 0:
            await ctx.send(embed=make_embed(description="価格は1以上にしてください。", color=discord.Color.red()))
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO role_shop (guild_id, role_id, price, description) VALUES (?, ?, ?, ?)",
                (ctx.guild.id, role.id, price, description),
            )
            await db.commit()
        from utils.helpers import format_number
        await ctx.send(embed=make_embed(
            description=f"✅ {role.mention} を **{format_number(price)} Kapi Coin** でショップに追加しました。",
            color=discord.Color.green(),
        ))

    @commands.command(name="removeroleshop", aliases=["ロールショップ削除"])
    @commands.has_permissions(administrator=True)
    async def removeroleshop(self, ctx, role: discord.Role):
        """ロールをショップから削除します（管理者専用）\n使い方: kapi removeroleshop @ロール"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM role_shop WHERE guild_id=? AND role_id=?",
                (ctx.guild.id, role.id),
            )
            await db.commit()
        await ctx.send(embed=make_embed(
            description=f"🗑️ {role.mention} をショップから削除しました。",
            color=discord.Color.orange(),
        ))

    @commands.command(name="roleshop", aliases=["ロールショップ"])
    async def roleshop(self, ctx):
        """Kapi Coinで購入できるロール一覧を表示します\n使い方: kapi roleshop"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT role_id, price, description FROM role_shop WHERE guild_id=? ORDER BY price ASC",
                (ctx.guild.id,),
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await ctx.send(embed=make_embed(description="ロールショップにアイテムがありません。", color=discord.Color.orange()))
            return

        from utils.helpers import format_number
        lines = []
        for role_id, price, desc in rows:
            role = ctx.guild.get_role(role_id)
            if role:
                line = f"• {role.mention} — **{format_number(price)} Kapi Coin**"
                if desc:
                    line += f"\n　{desc}"
                lines.append(line)

        embed = make_embed(
            title="🏪 ロールショップ",
            description="\n".join(lines) if lines else "有効なロールがありません。",
            color=discord.Color.gold(),
            footer="`kapi buyrole @ロール` で購入",
        )
        await ctx.send(embed=embed)

    @commands.command(name="buyrole", aliases=["ロール購入"])
    async def buyrole(self, ctx, role: discord.Role):
        """Kapi Coinでロールを購入します\n使い方: kapi buyrole @ロール"""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT price FROM role_shop WHERE guild_id=? AND role_id=?",
                (ctx.guild.id, role.id),
            ) as cur:
                row = await cur.fetchone()

        if not row:
            await ctx.send(embed=make_embed(description=f"{role.mention} はショップにありません。`kapi roleshop` で一覧を確認してください。", color=discord.Color.red()))
            return

        price = row[0]

        if role in ctx.author.roles:
            await ctx.send(embed=make_embed(description=f"すでに {role.mention} を持っています。", color=discord.Color.orange()))
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO economy (user_id, guild_id) VALUES (?, ?)",
                (ctx.author.id, ctx.guild.id),
            )
            await db.commit()
            async with db.execute(
                "SELECT balance FROM economy WHERE user_id=? AND guild_id=?",
                (ctx.author.id, ctx.guild.id),
            ) as cur:
                bal_row = await cur.fetchone()

        balance = bal_row[0] if bal_row else 0
        from utils.helpers import format_number

        if balance < price:
            await ctx.send(embed=make_embed(
                description=f"残高が不足しています。\n必要: **{format_number(price)} Kapi Coin** / 所持: **{format_number(balance)} Kapi Coin**",
                color=discord.Color.red(),
            ))
            return

        try:
            await ctx.author.add_roles(role, reason="ロールショップで購入")
        except discord.Forbidden:
            await ctx.send(embed=make_embed(description="ロールを付与する権限がありません。", color=discord.Color.red()))
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE economy SET balance = balance - ? WHERE user_id=? AND guild_id=?",
                (price, ctx.author.id, ctx.guild.id),
            )
            await db.commit()

        await ctx.send(embed=make_embed(
            title="🛒 ロール購入完了！",
            description=f"✅ {role.mention} を購入しました！\n**-{format_number(price)} Kapi Coin**",
            color=discord.Color.green(),
            footer=f"残高: {format_number(balance - price)} Kapi Coin",
        ))


async def setup(bot):
    await bot.add_cog(Roles(bot))
