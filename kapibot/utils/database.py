import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "kapibot.db")


async def get_db():
    return await aiosqlite.connect(DB_PATH)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS economy (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                balance INTEGER DEFAULT 0,
                last_daily TEXT,
                last_work TEXT,
                PRIMARY KEY (user_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS shop (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price INTEGER NOT NULL,
                role_id INTEGER,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, guild_id, item_id)
            );

            CREATE TABLE IF NOT EXISTS levels (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                total_messages INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS level_roles (
                guild_id INTEGER NOT NULL,
                level INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, level)
            );

            CREATE TABLE IF NOT EXISTS gacha_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                rarity TEXT NOT NULL,
                weight INTEGER DEFAULT 10,
                role_id INTEGER,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS gacha_inventory (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, guild_id, item_id)
            );

            CREATE TABLE IF NOT EXISTS role_selections (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                selected_at TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS role_panels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                title TEXT DEFAULT 'ロール選択',
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS role_panel_roles (
                panel_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                label TEXT,
                emoji TEXT,
                PRIMARY KEY (panel_id, role_id)
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                status TEXT DEFAULT 'open',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS ticket_settings (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER,
                log_channel_id INTEGER,
                support_role_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS spam_settings (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                message_limit INTEGER DEFAULT 5,
                time_window INTEGER DEFAULT 5,
                timeout_duration INTEGER DEFAULT 60
            );

            CREATE TABLE IF NOT EXISTS once_roles (
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                description TEXT,
                PRIMARY KEY (guild_id, role_id)
            );

            CREATE TABLE IF NOT EXISTS once_role_claims (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                claimed_at TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id, role_id)
            );

            CREATE TABLE IF NOT EXISTS self_roles (
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                description TEXT,
                PRIMARY KEY (guild_id, role_id)
            );

            CREATE TABLE IF NOT EXISTS role_shop (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                price INTEGER NOT NULL,
                description TEXT,
                UNIQUE(guild_id, role_id)
            );

            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT DEFAULT 'kapi ',
                log_channel_id INTEGER,
                welcome_channel_id INTEGER,
                leave_channel_id INTEGER,
                welcome_message TEXT,
                leave_message TEXT,
                level_up_channel_id INTEGER,
                level_up_message TEXT,
                xp_rate INTEGER DEFAULT 10,
                xp_cooldown INTEGER DEFAULT 60
            );
        """)
        await db.commit()
