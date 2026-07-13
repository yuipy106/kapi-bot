import discord
from discord.ext import commands
import aiosqlite
from datetime import datetime
from utils.database import DB_PATH
from utils.helpers import make_embed


class CloseButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="チケットを閉じる", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("このボタンはチケットチャンネル専用です。", ephemeral=True)
            return

        if not (
            interaction.user.guild_permissions.manage_channels
            or interaction.channel.overwrites_for(interaction.user).send_messages
        ):
            await interaction.response.send_message("このチケットを閉じる権限がありません。", ephemeral=True)
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE tickets SET status='closed' WHERE channel_id=? AND guild_id=?",
                (interaction.channel.id, interaction.guild.id),
            )
            async with db.execute(
                "SELECT log_channel_id FROM ticket_settings WHERE guild_id=?",
                (interaction.guild.id,),
            ) as cur:
                row = await cur.fetchone()
            await db.commit()

        await interaction.response.send_message(
            embed=make_embed(description="チケットを閉じています...", color=discord.Color.orange())
        )

        if row and row[0]:
            log_channel = interaction.guild.get_channel(row[0])
            if log_channel:
                embed = make_embed(
                    title="🎫 チケットクローズ",
                    description=f"チャンネル: {interaction.channel.mention}\nクローズ: {interaction.user.mention}",
                    color=discord.Color.red(),
                    timestamp=True,
                )
                await log_channel.send(embed=embed)

        await interaction.channel.delete(reason=f"チケットクローズ by {interaction.user}")


class CreateTicketButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="チケットを作成", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=? AND status='open'",
                (guild.id, user.id),
            ) as cur:
                existing = await cur.fetchone()

        if existing:
            channel = guild.get_channel(existing[0])
            if channel:
                await interaction.response.send_message(
                    embed=make_embed(
                        description=f"すでにオープン中のチケットがあります: {channel.mention}",
                        color=discord.Color.orange(),
                    ),
                    ephemeral=True,
                )
                return

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT category_id, support_role_id FROM ticket_settings WHERE guild_id=?",
                (guild.id,),
            ) as cur:
                settings = await cur.fetchone()

        category_id = settings[0] if settings else None
        support_role_id = settings[1] if settings else None
        category = guild.get_channel(category_id) if category_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if support_role_id:
            support_role = guild.get_role(support_role_id)
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await guild.create_text_channel(
            name=f"ticket-{user.name}",
            category=category,
            overwrites=overwrites,
            reason=f"チケット作成 by {user}",
        )

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO tickets (guild_id, channel_id, user_id, created_at) VALUES (?, ?, ?, ?)",
                (guild.id, channel.id, user.id, datetime.utcnow().isoformat()),
            )
            await db.commit()

        embed = make_embed(
            title="🎫 チケット",
            description=f"{user.mention} のチケットです。\nサポートスタッフが確認次第対応します。\n\n完了したら下のボタンでチケットを閉じてください。",
            color=discord.Color.green(),
            timestamp=True,
        )
        await channel.send(embed=embed, view=CloseButton())

        await interaction.response.send_message(
            embed=make_embed(
                description=f"チケットを作成しました: {channel.mention}",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(CreateTicketButton())
        self.bot.add_view(CloseButton())

    @commands.command(name="ticketpanel", aliases=["チケットパネル"])
    @commands.has_permissions(administrator=True)
    async def ticketpanel(self, ctx, *, description: str = "サポートが必要な場合はボタンを押してチケットを作成してください。"):
        """チケット作成パネルを設置します（管理者専用）"""
        embed = make_embed(
            title="🎫 サポートチケット",
            description=description,
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed, view=CreateTicketButton())

    @commands.command(name="ticketsetup", aliases=["チケット設定"])
    @commands.has_permissions(administrator=True)
    async def ticketsetup(self, ctx, category: discord.CategoryChannel = None, log_channel: discord.TextChannel = None, support_role: discord.Role = None):
        """チケットの設定をします（管理者専用）"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT OR REPLACE INTO ticket_settings (guild_id, category_id, log_channel_id, support_role_id)
                   VALUES (?, ?, ?, ?)""",
                (
                    ctx.guild.id,
                    category.id if category else None,
                    log_channel.id if log_channel else None,
                    support_role.id if support_role else None,
                ),
            )
            await db.commit()

        embed = make_embed(
            title="✅ チケット設定完了",
            color=discord.Color.green(),
        )
        embed.add_field(name="カテゴリ", value=category.name if category else "未設定", inline=True)
        embed.add_field(name="ログチャンネル", value=log_channel.mention if log_channel else "未設定", inline=True)
        embed.add_field(name="サポートロール", value=support_role.mention if support_role else "未設定", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="closeticket", aliases=["チケット閉じる"])
    @commands.has_permissions(manage_channels=True)
    async def closeticket(self, ctx):
        """チケットを閉じます（サポートスタッフ専用）"""
        if not ctx.channel.name.startswith("ticket-"):
            await ctx.send(embed=make_embed(description="このコマンドはチケットチャンネルでのみ使用できます。", color=discord.Color.red()))
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE tickets SET status='closed' WHERE channel_id=? AND guild_id=?",
                (ctx.channel.id, ctx.guild.id),
            )
            await db.commit()

        await ctx.send(embed=make_embed(description="チケットを閉じています...", color=discord.Color.orange()))
        await ctx.channel.delete(reason=f"チケットクローズ by {ctx.author}")


async def setup(bot):
    await bot.add_cog(Tickets(bot))
