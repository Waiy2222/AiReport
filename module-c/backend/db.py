"""PostgreSQL 连接管理（asyncpg）"""
import os
import asyncpg

_pool: asyncpg.Pool | None = None

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_news")


async def init_db():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_db() first.")
    return _pool
