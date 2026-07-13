import discord
from datetime import datetime


def make_embed(
    title: str = None,
    description: str = None,
    color: discord.Color = discord.Color.blurple(),
    footer: str = None,
    thumbnail: str = None,
    image: str = None,
    author: str = None,
    author_icon: str = None,
    timestamp: bool = False,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    if footer:
        embed.set_footer(text=footer)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    if author:
        embed.set_author(name=author, icon_url=author_icon)
    if timestamp:
        embed.timestamp = datetime.utcnow()
    return embed


def xp_for_level(level: int) -> int:
    return 5 * (level ** 2) + 50 * level + 100


def level_from_xp(xp: int) -> int:
    level = 0
    while xp >= xp_for_level(level):
        xp -= xp_for_level(level)
        level += 1
    return level


def xp_progress(total_xp: int):
    level = 0
    remaining = total_xp
    while remaining >= xp_for_level(level):
        remaining -= xp_for_level(level)
        level += 1
    return level, remaining, xp_for_level(level)


def format_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)
