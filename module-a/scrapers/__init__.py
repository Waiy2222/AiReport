"""Module A scrapers — one module per data source."""

import json
import logging
from datetime import datetime, timezone

import asyncpg

logger = logging.getLogger(__name__)


async def _insert_items(
    pool: asyncpg.Pool,
    source: str,
    items: list[dict],
    batch_id,
) -> int:
    """Insert items into raw_items, skipping duplicates on url.

    Returns the count of newly inserted rows.
    """
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
                        VALUES
                            ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                        ON CONFLICT (url) DO NOTHING
                        RETURNING id
                        """,
                        source,
                        item["title"],
                        item["url"],
                        item.get("content", ""),
                        item.get("author", ""),
                        item["published_at"],
                        now,
                        json.dumps(item.get("metadata", {})),
                        batch_id,
                    )
                    if result is not None:
                        count += 1
                except Exception:
                    logger.debug("Skipping malformed item", exc_info=True)

    return count


from .github import fetch as github_fetch
from .hackernews import fetch as hackernews_fetch
from .rss import fetch as rss_fetch
from .reddit import fetch as reddit_fetch

SCRAPERS = {
    "github": github_fetch,
    "hackernews": hackernews_fetch,
    "rss": rss_fetch,
    "reddit": reddit_fetch,
}
