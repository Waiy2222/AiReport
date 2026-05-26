"""Reddit AI subreddits scraper."""

import logging
from datetime import datetime, timezone

import httpx

from . import _insert_items

logger = logging.getLogger(__name__)

REDDIT_URL = (
    "https://www.reddit.com/r/artificial+MachineLearning+LocalLLaMA/hot.json"
)
USER_AGENT = "ai-news-briefing/1.0 (by /u/ai_news_bot)"


def _parse_post(post: dict, since: datetime) -> dict | None:
    """Parse a Reddit post data dict. Returns None if it should be skipped."""
    try:
        created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
    except (KeyError, TypeError, OSError):
        logger.debug("Reddit post missing created_utc field")
        return None

    if created < since:
        return None

    title = post.get("title", "")
    permalink = post.get("permalink", "")
    if not title or not permalink:
        return None

    # Build full Reddit URL
    url = f"https://www.reddit.com{permalink}"

    return {
        "title": title,
        "url": url,
        "content": post.get("selftext") or "",
        "author": post.get("author") or "[deleted]",
        "published_at": created.isoformat(),
        "metadata": {
            "score": post.get("score", 0),
            "num_comments": post.get("num_comments", 0),
            "subreddit": post.get("subreddit", ""),
            "upvote_ratio": post.get("upvote_ratio", 0.0),
            "is_self": post.get("is_self", False),
        },
    }


async def fetch(pool, since: datetime, batch_id) -> int:
    """Fetch trending posts from AI subreddits and insert into raw_items.

    Returns the number of newly inserted items (0 on failure).
    """
    headers = {"User-Agent": USER_AGENT}
    params = {"limit": 15, "raw_json": 1}

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(REDDIT_URL, params=params, headers=headers)

            if resp.status_code == 429:
                logger.warning("Reddit API rate-limited (HTTP 429)")
                return 0

            resp.raise_for_status()
            data = resp.json()
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        logger.warning("Reddit API request failed: %s", exc)
        return 0
    except Exception:
        logger.exception("Unexpected error fetching Reddit posts")
        return 0

    children = data.get("data", {}).get("children", [])
    if not children:
        logger.warning("Reddit returned no post data")
        return 0

    items = []
    for child in children:
        post_data = child.get("data", {})
        parsed = _parse_post(post_data, since)
        if parsed:
            items.append(parsed)

    logger.info("Reddit: %d posts parsed (from %d raw children)", len(items), len(children))
    return await _insert_items(pool, "reddit", items, batch_id)
