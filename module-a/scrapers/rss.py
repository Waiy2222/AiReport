"""RSS 多源并发抓取 — 机器之心、量子位、ArXiv、HuggingFace 等"""
import asyncio
import logging
import uuid as uuid_lib
from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from scrapers.filters import filter_items_by_title

logger = logging.getLogger(__name__)

RSS_SOURCES = [
    {"name": "arxiv",          "url": "https://arxiv.org/rss/cs.AI"},
    {"name": "jiqizhixin",     "url": "https://www.jiqizhixin.com/rss"},
    {"name": "qbitai",         "url": "https://www.qbitai.com/feed"},
    {"name": "huggingface",    "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "techcrunch_ai",  "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
]


async def fetch_single_rss(source: dict) -> list[dict]:
    """同步抓取单个 RSS 源（在线程池运行以避免阻塞）"""
    loop = asyncio.get_running_loop()
    try:
        feed = await loop.run_in_executor(None, feedparser.parse, source["url"])
    except Exception as e:
        logger.warning(f"RSS [{source['name']}] parse error: {e}")
        return []

    if feed.bozo and not feed.entries:
        logger.warning(f"RSS [{source['name']}] bozo: {feed.bozo_exception}")
        return []

    return [
        {**entry, "_source_name": source["name"]}
        for entry in feed.entries
    ]


async def fetch_rss(since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """主函数：并发抓取所有 RSS 源 → 过滤 → 映射"""
    tasks = [fetch_single_rss(src) for src in RSS_SOURCES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_entries = []
    for i, result in enumerate(results):
        source_name = RSS_SOURCES[i]["name"]
        if isinstance(result, Exception):
            logger.warning(f"RSS [{source_name}] failed: {result}")
            continue
        all_entries.extend(result)

    # 过滤时间
    filtered = [e for e in all_entries if _entry_time(e) >= since]

    # 关键词过滤
    ai_entries = filter_items_by_title(filtered, "title")

    # 映射为 raw_items
    return to_raw_items(ai_entries, "rss", batch_id)


def to_raw_items(entries: list[dict], source_name: str, batch_id: uuid_lib.UUID) -> list[dict]:
    """将 RSS entries 映射为 raw_items 行"""
    result = []
    for entry in entries:
        actual_source = entry.pop("_source_name", source_name)
        result.append({
            "source": actual_source,
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "content": _clean_html(entry.get("summary", "")),
            "author": entry.get("author", ""),
            "published_at": _parse_rss_time(entry),
            "batch_id": batch_id,
            "metadata": {},
        })
    return result


def _entry_time(entry: dict) -> datetime:
    """从 RSS entry 提取 published 时间"""
    return _parse_rss_time(entry)


def _parse_rss_time(entry: dict) -> datetime:
    """解析 RSS 时间字段到 UTC datetime"""
    parsed = entry.get("published_parsed")
    if parsed and len(parsed) >= 6:
        try:
            ts = timegm(parsed[:6] + (0, 0, 0))
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass
    # fallback: 尝试字符串解析
    published_str = entry.get("published", "")
    if published_str:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(published_str)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)


def _clean_html(text: str) -> str:
    """清理 HTML 标签，保留纯文本"""
    if not text:
        return ""
    import re
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


async def fetch(pool, since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """标准 scraper 接口"""
    return await fetch_rss(since, batch_id)
