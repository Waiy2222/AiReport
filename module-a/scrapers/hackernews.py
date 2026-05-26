"""HackerNews top AI stories scraper."""

import logging
from datetime import datetime, timezone

import httpx

from . import _insert_items

logger = logging.getLogger(__name__)

HN_TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"

AI_KEYWORDS = (
    "ai", "llm", "gpt", "claude", "openai", "deepseek", "anthropic",
    "chatgpt", "copilot", "gemini", "mistral", "artificial intelligence",
    "machine learning", "transformer", "diffusion", "langchain", "llama",
    "stable diffusion", "rag", "deep learning", "neural network",
    "fine-tune", "fine tuning", "pretrain", "pre-train", "foundation model",
    "agent", "multi-modal", "multimodal", "text-to-image", "text to image",
    "tokenizer", "embedding", "vector database",
)


def _is_ai_related(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in AI_KEYWORDS)


def _parse_story(story: dict, story_id: int, since: datetime) -> dict | None:
    """Parse a single HN story item. Returns None if it should be skipped."""
    if not story or story.get("type") != "story":
        return None

    title = story.get("title", "")
    if not title:
        return None

    published = datetime.fromtimestamp(story.get("time", 0), tz=timezone.utc)
    if published < since:
        return None

    if not _is_ai_related(title):
        return None

    url = story.get("url") or f"https://news.ycombinator.com/item?id={story_id}"

    return {
        "title": title,
        "url": url,
        "content": story.get("text") or "",
        "author": story.get("by") or "",
        "published_at": published,
        "metadata": {
            "score": story.get("score", 0),
            "descendants": story.get("descendants", 0),
            "type": story.get("type", "story"),
            "hn_id": story_id,
        },
    }


async def fetch(pool, since: datetime, batch_id) -> int:
    """Fetch AI-related top stories from HackerNews and insert into raw_items.

    Returns the number of newly inserted items (0 on failure).
    """
    headers = {"User-Agent": "ai-news-briefing/1.0"}

    # 1. Get top story IDs
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(HN_TOP_STORIES, headers=headers)
            resp.raise_for_status()
            story_ids = resp.json()
    except Exception:
        logger.exception("Failed to fetch HackerNews top story list")
        return 0

    if not story_ids:
        logger.warning("HackerNews returned empty story list")
        return 0

    # Check up to the first 150 stories for AI relevance
    story_ids = story_ids[:150]
    logger.info("HackerNews: checking %d stories for AI relevance", len(story_ids))

    # 2. Fetch individual stories
    items = []
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for sid in story_ids:
                try:
                    resp = await client.get(
                        HN_ITEM.format(item_id=sid), headers=headers
                    )
                    resp.raise_for_status()
                    story = resp.json()
                    parsed = _parse_story(story, sid, since)
                    if parsed:
                        items.append(parsed)
                except Exception:
                    # Individual item failures are non-fatal
                    logger.debug("Failed to fetch HN item %d", sid, exc_info=True)
                    continue
    except Exception:
        logger.exception("Unexpected error fetching HackerNews items")
        # Return whatever we managed to collect so far
        return await _insert_items(pool, "hackernews", items, batch_id)

    logger.info("HackerNews: %d AI-related stories found", len(items))
    return await _insert_items(pool, "hackernews", items, batch_id)
