"""统一调度器 — 并发执行 scraper + 去重 + 批量写入"""
import asyncio
import logging
import uuid as uuid_lib
from datetime import datetime, timezone

import asyncpg

from scrapers.github import fetch_github
from scrapers.hackernews import fetch_hackernews
from scrapers.rss import fetch_rss

logger = logging.getLogger(__name__)

SCRAPER_TIMEOUT = 60  # 单个 scraper 超时秒数

# scraper 注册表
_SCRAPER_MAP = {
    "github": fetch_github,
    "hackernews": fetch_hackernews,
    "rss": fetch_rss,
}


async def run_all_scrapers(
    since: datetime,
    batch_id: uuid_lib.UUID,
    enabled_sources: list[str],
) -> tuple[list[dict], dict]:
    """并发执行所有启用的 scraper，单源失败/超时不阻塞其他"""
    stats: dict[str, int] = {}

    async def _run_one(name: str):
        scraper = _SCRAPER_MAP.get(name)
        if scraper is None:
            logger.warning(f"Unknown scraper: {name}")
            stats[name] = 0
            return []
        try:
            items = await asyncio.wait_for(scraper(since, batch_id), timeout=SCRAPER_TIMEOUT)
            stats[name] = len(items)
            return items
        except asyncio.TimeoutError:
            logger.warning(f"Scraper [{name}] timed out after {SCRAPER_TIMEOUT}s")
            stats[name] = 0
            return []
        except Exception as e:
            logger.warning(f"Scraper [{name}] failed: {e}")
            stats[name] = 0
            return []

    tasks = [_run_one(name) for name in enabled_sources]
    results = await asyncio.gather(*tasks)

    all_items = []
    for items in results:
        all_items.extend(items)

    # 跨源去重
    unique_items = dedup_by_url(all_items)

    return unique_items, stats


def dedup_by_url(items: list[dict]) -> list[dict]:
    """按 URL 去重，保留首次出现的条目"""
    seen: set[str] = set()
    result = []
    for item in items:
        url = item.get("url", "")
        if not url:
            result.append(item)
        elif url not in seen:
            seen.add(url)
            result.append(item)
    return result


async def bulk_insert(pool: asyncpg.Pool, items: list[dict]) -> int:
    """批量插入 raw_items 表，用 ON CONFLICT 防重复，支持 embedding 列"""
    if not items:
        return 0

    rows = [
        (
            item["source"],
            item["title"],
            item["url"],
            item.get("content", ""),
            item.get("author", ""),
            item["published_at"],
            item["batch_id"],
            item.get("metadata", {}),
            item.get("embedding"),
        )
        for item in items
    ]

    # 格式化 embedding 为 pgvector 字符串（NULL 保持 None）
    formatted_rows = []
    for row in rows:
        *rest, embedding = row
        if embedding is not None:
            embedding_str = f"[{','.join(str(x) for x in embedding)}]"
        else:
            embedding_str = None
        formatted_rows.append(tuple(rest) + (embedding_str,))

    async with pool.acquire() as conn:
        result = await conn.executemany(
            """
            INSERT INTO raw_items (source, title, url, content, author, published_at, batch_id, metadata, embedding)
            SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9::vector
            WHERE NOT EXISTS (
                SELECT 1 FROM raw_items WHERE url = $3 AND batch_id = $7
            )
            """,
            formatted_rows,
        )
    inserted = sum(1 for part in result.split("INSERT") if "0 1" in part)
    return inserted


async def run_pipeline(
    pool: asyncpg.Pool,
    since: datetime,
    batch_id: uuid_lib.UUID,
    enabled_sources: list[str],
) -> dict:
    """Phase 2 完整流程：抓取 → 去重 → LLM 筛选 → embedding → 写入"""
    # Step 1: 并发抓取
    items, per_source = await run_all_scrapers(since, batch_id, enabled_sources)

    if not items:
        return {"fetched": 0, "llm_filtered": False, "per_source": per_source}

    # Step 2: LLM 筛选 + embedding 生成
    from llm_filter import filter_and_enrich
    filtered, llm_used = await filter_and_enrich(pool, items)

    # Step 3: 批量写入（含 embedding）
    inserted = await bulk_insert(pool, filtered)

    return {
        "fetched": inserted,
        "llm_filtered": llm_used,
        "per_source": per_source,
    }
