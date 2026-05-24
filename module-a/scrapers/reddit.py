"""Reddit 抓取 — AI/ML 子版块新帖（可选 P1）"""
import asyncio
import logging
import uuid as uuid_lib
from datetime import datetime, timezone

import httpx

from scrapers.filters import filter_items_by_title

logger = logging.getLogger(__name__)

SUBREDDITS = ["MachineLearning", "artificial", "LocalLLaMA", "OpenSource"]

USER_AGENT = "AiReport/1.0 (by u/ai_report_bot)"


async def fetch_subreddit(client: httpx.AsyncClient, name: str, limit: int = 25) -> list[dict]:
    """抓取单个子版块新帖"""
    url = f"https://www.reddit.com/r/{name}/new.json"
    headers = {"User-Agent": USER_AGENT}
    try:
        r = await client.get(url, headers=headers, params={"limit": limit})
        r.raise_for_status()
        data = r.json()
        return data.get("data", {}).get("children", [])
    except Exception as e:
        logger.warning(f"Reddit r/{name} failed: {e}")
        return []


async def fetch_reddit(since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """主函数：并发抓取多个子版块 → 过滤 → 映射"""
    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [fetch_subreddit(client, sub) for sub in SUBREDDITS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_posts = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"Reddit r/{SUBREDDITS[i]} exception: {result}")
            continue
        all_posts.extend(result)

    # 时间过滤
    recent = [p for p in all_posts if _post_time(p) >= since]

    # 关键词过滤
    ai_posts = filter_items_by_title(recent, "data.title")

    return to_raw_items(ai_posts, batch_id)


def to_raw_items(posts: list[dict], batch_id: uuid_lib.UUID) -> list[dict]:
    """将 Reddit post 映射为 raw_items 行"""
    result = []
    for post in posts:
        data = post.get("data", {})
        external_url = data.get("url", "")
        permalink = data.get("permalink", "")

        # Reddit 帖子链接；外部链接存入 metadata
        url = f"https://www.reddit.com{permalink}" if permalink else external_url
        content = data.get("selftext", "")

        result.append({
            "source": "reddit",
            "title": data.get("title", ""),
            "url": url,
            "content": content[:2000] if content else "",  # 截断长文本
            "author": data.get("author", ""),
            "published_at": _parse_reddit_time(data.get("created_utc")),
            "batch_id": batch_id,
            "metadata": {
                "ups": data.get("ups", 0),
                "comments": data.get("num_comments", 0),
                "subreddit": data.get("subreddit", ""),
                "external_url": external_url if external_url != url else "",
            },
        })
    return result


def _post_time(post: dict) -> datetime:
    return _parse_reddit_time(post.get("data", {}).get("created_utc"))


def _parse_reddit_time(ts: float | None) -> datetime:
    """Unix timestamp (float) → UTC datetime"""
    if ts is None:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return datetime.now(timezone.utc)
