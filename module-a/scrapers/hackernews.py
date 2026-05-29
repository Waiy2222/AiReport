"""Hacker News 抓取 — Top Stories + 关键词过滤"""
import asyncio
import logging
import uuid as uuid_lib
from datetime import datetime, timezone

import httpx

from scrapers.filters import filter_items_by_title

logger = logging.getLogger(__name__)

TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"


async def get_top_stories(limit: int = 100) -> list[int]:
    """获取 HN 热门 story ID 列表"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(TOP_STORIES_URL)
            r.raise_for_status()
            ids = r.json()
            return ids[:limit]
    except Exception as e:
        logger.warning(f"HN topstories failed: {e}")
        return []


async def get_item(client: httpx.AsyncClient, item_id: int, sem: asyncio.Semaphore) -> dict | None:
    """获取单条 story 详情（带限流）"""
    async with sem:
        try:
            r = await client.get(ITEM_URL.format(item_id=item_id))
            r.raise_for_status()
            return r.json()
        except Exception:
            return None


async def fetch_items_concurrent(item_ids: list[int], concurrency: int = 20) -> list[dict]:
    """并发获取多条 story 详情"""
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [get_item(client, iid, sem) for iid in item_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, dict) and r is not None]


async def fetch_hackernews(since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """主函数：获取 top stories → 并发取详情 → 过滤 → 映射"""
    ids = await get_top_stories(300)
    if not ids:
        return []

    items = await fetch_items_concurrent(ids, concurrency=20)

    # 时间过滤
    recent = [i for i in items if _hn_time(i) >= since]

    # 关键词过滤
    ai_items = filter_items_by_title(recent, "title")

    return to_raw_items(ai_items, batch_id)


def to_raw_items(items: list[dict], batch_id: uuid_lib.UUID) -> list[dict]:
    """将 HN items 映射为 raw_items 行"""
    result = []
    for item in items:
        result.append({
            "source": "hackernews",
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("text", ""),
            "author": item.get("by", ""),
            "published_at": _parse_hn_time(item.get("time")),
            "batch_id": batch_id,
            "metadata": {
                "score": item.get("score", 0),
                "comments": item.get("descendants", 0),
            },
        })
    return result


def _hn_time(item: dict) -> datetime:
    """从 HN item 提取时间"""
    return _parse_hn_time(item.get("time"))


def _parse_hn_time(ts: int | None) -> datetime:
    """Unix timestamp → UTC datetime"""
    if ts is None:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return datetime.now(timezone.utc)


async def fetch(pool, since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """标准 scraper 接口"""
    return await fetch_hackernews(since, batch_id)
