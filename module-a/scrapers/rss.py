"""RSS 多源并发抓取 — 科技 + 时事 + 国际 + 体育"""
import asyncio
import logging
import re
import uuid as uuid_lib
from calendar import timegm
from datetime import datetime, timezone

import feedparser

logger = logging.getLogger(__name__)

RSS_SOURCES = [
    # ── 科技（中文）──
    {"name": "qbitai",         "url": "https://www.qbitai.com/feed",           "category": "科技"},
    {"name": "36kr",           "url": "https://36kr.com/feed",                 "category": "科技"},
    {"name": "sspai",          "url": "https://sspai.com/feed",                "category": "科技"},
    {"name": "ithome",         "url": "https://www.ithome.com/rss/",           "category": "科技"},
    {"name": "ifanr",          "url": "https://www.ifanr.com/feed",            "category": "科技"},
    {"name": "solidot",        "url": "https://www.solidot.org/index.rss",    "category": "科技"},
    {"name": "leiphone",       "url": "https://www.leiphone.com/feed",         "category": "科技"},
    {"name": "techcrunch_ai",  "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "category": "科技"},

    # ── 时事（中文）──
    {"name": "people",         "url": "http://www.people.com.cn/rss/politics.xml", "category": "时事"},

    # ── 国际（中文）──
    {"name": "bbc_zh",         "url": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml", "category": "国际"},
    {"name": "voa_zh",         "url": "https://www.voachinese.com/api/",       "category": "国际"},

    # ── 体育 ──
    {"name": "espn",           "url": "https://www.espn.com/espn/rss/news",   "category": "体育"},
]


async def fetch_single_rss(source: dict) -> list[dict]:
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
        {**entry, "_source_name": source["name"], "_category": source.get("category", "")}
        for entry in feed.entries
    ]


async def fetch_rss(since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    tasks = [fetch_single_rss(src) for src in RSS_SOURCES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_entries = []
    for i, result in enumerate(results):
        source_name = RSS_SOURCES[i]["name"]
        if isinstance(result, Exception):
            logger.warning(f"RSS [{source_name}] failed: {result}")
            continue
        all_entries.extend(result)

    filtered = [e for e in all_entries if _entry_time(e) >= since]
    return to_raw_items(filtered, "rss", batch_id)


def to_raw_items(entries: list[dict], source_name: str, batch_id: uuid_lib.UUID) -> list[dict]:
    result = []
    for entry in entries:
        actual_source = entry.pop("_source_name", source_name)
        category = entry.pop("_category", "")
        result.append({
            "source": actual_source,
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "content": _clean_html(entry.get("summary", "")),
            "author": entry.get("author", ""),
            "published_at": _parse_rss_time(entry),
            "batch_id": batch_id,
            "metadata": {"category": category},
        })
    return result


def _entry_time(entry: dict) -> datetime:
    return _parse_rss_time(entry)


def _parse_rss_time(entry: dict) -> datetime:
    parsed = entry.get("published_parsed")
    if parsed and len(parsed) >= 6:
        try:
            ts = timegm(parsed[:6] + (0, 0, 0))
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass
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
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


async def fetch(pool, since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    return await fetch_rss(since, batch_id)
