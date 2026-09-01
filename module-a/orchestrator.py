"""统一调度器 — 并发执行 scraper + 去重 + 批量写入"""
import asyncio
import json
import logging
import uuid as uuid_lib
from datetime import datetime, timezone

import asyncpg

from scrapers.github import fetch_github
from scrapers.hackernews import fetch_hackernews
from scrapers.rss import fetch_rss, search_google_news

logger = logging.getLogger(__name__)

SCRAPER_TIMEOUT = 45  # 单个 scraper 超时秒数（降低以减少排队等待）

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
    """批量插入 raw_items 表，用 ON CONFLICT 防重复（无 embedding 列，因 pgvector 未安装）"""
    if not items:
        return 0

    now = datetime.now(timezone.utc)
    count = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for item in items:
                try:
                    result = await conn.fetchval(
                        """
                        INSERT INTO raw_items
                            (source, title, url, content, author,
                             published_at, fetched_at, metadata, batch_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                        ON CONFLICT (url) DO UPDATE SET batch_id = EXCLUDED.batch_id
                        RETURNING id
                        """,
                        item["source"],
                        item["title"],
                        item["url"],
                        item.get("content", ""),
                        item.get("author", ""),
                        item["published_at"],
                        now,
                        json.dumps(item.get("metadata", {})),
                        item["batch_id"],
                    )
                    if result is not None:
                        count += 1
                except Exception:
                    logger.debug("Skipping malformed item in bulk_insert: %s",
                                 item.get("title", "?")[:60], exc_info=True)
    return count


async def run_pipeline(
    pool: asyncpg.Pool,
    since: datetime,
    batch_id: uuid_lib.UUID,
    enabled_sources: list[str],
    search_keywords: list[str] | None = None,
) -> dict:
    """Phase 2 完整流程：抓取 → 去重 → (可选)LLM筛选 → 写入

    v2 优化：
    - RSS 和关键词搜索并发执行（节省 50% 网络等待）
    - 个性化简报跳过 LLM 筛选（pipeline 自行过滤，节省 5-15s）
    """
    # Step 1: RSS + 关键词搜索 并发执行
    rss_task = asyncio.create_task(run_all_scrapers(since, batch_id, enabled_sources)) if enabled_sources else None
    search_task = asyncio.create_task(search_google_news(search_keywords, since, batch_id)) if search_keywords else None

    items: list[dict] = []
    per_source: dict[str, int] = {}

    if rss_task:
        rss_items, per_source = await rss_task
        items.extend(rss_items)

    if search_task:
        try:
            search_items = await search_task
            if search_items:
                items.extend(search_items)
                per_source["google_news_search"] = len(search_items)
                logger.info(f"Google News search: {len(search_items)} items for {search_keywords}")
        except Exception as e:
            logger.warning(f"Google News search failed (non-blocking): {e}")

    if not items:
        return {"fetched": 0, "llm_filtered": False, "per_source": per_source}

    # 去重
    items = dedup_by_url(items)

    # 政治敏感内容过滤
    from scrapers.filters import filter_political
    before_political = len(items)
    items = filter_political(items)
    if before_political > len(items):
        per_source["political_rejected"] = before_political - len(items)

    if not items:
        return {"fetched": 0, "llm_filtered": False, "per_source": per_source}

    # Step 2: LLM 筛选（个性化简报跳过，pipeline 自行过滤）
    is_personalized = bool(search_keywords)
    if is_personalized:
        # 个性化简报：跳过 LLM 筛选，直接写入（阈值3.0等于不过滤）
        for it in items:
            meta = it.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            it["metadata"] = meta
        inserted = await bulk_insert(pool, items)
        logger.info(f"Personalized: {inserted} items written (LLM filter skipped)")
        return {"fetched": inserted, "llm_filtered": False, "per_source": per_source}

    from llm_filter import filter_and_enrich
    filtered, llm_used = await filter_and_enrich(pool, items, threshold=6.0)
    inserted = await bulk_insert(pool, filtered)

    return {
        "fetched": inserted,
        "llm_filtered": llm_used,
        "per_source": per_source,
    }
