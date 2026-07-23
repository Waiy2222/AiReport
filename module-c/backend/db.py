"""PostgreSQL 连接管理（asyncpg）"""
import json
import os
import asyncpg

_pool: asyncpg.Pool | None = None

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_news")


async def _init_conn(conn):
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def init_db():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10, init=_init_conn)


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_db() first.")
    return _pool


async def migrate_personalized_briefings(pool: asyncpg.Pool):
    """为 briefings 表添加个性化简报所需字段（幂等，跳过已存在的列）"""
    async with pool.acquire() as conn:
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name='briefings'"
        )
        existing = {r["column_name"] for r in cols}

        if "requested_by" not in existing:
            await conn.execute("ALTER TABLE briefings ADD COLUMN requested_by VARCHAR")
            print("[db] Added column: briefings.requested_by")

        if "interest_text" not in existing:
            await conn.execute("ALTER TABLE briefings ADD COLUMN interest_text TEXT")
            print("[db] Added column: briefings.interest_text")

        if "interest_tags" not in existing:
            await conn.execute("ALTER TABLE briefings ADD COLUMN interest_tags JSONB DEFAULT '[]'::jsonb")
            print("[db] Added column: briefings.interest_tags")

        if "is_personalized" not in existing:
            await conn.execute("ALTER TABLE briefings ADD COLUMN is_personalized BOOLEAN DEFAULT false")
            print("[db] Added column: briefings.is_personalized")

        print("[db] Personalized briefing columns ready")
