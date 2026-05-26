"""GitHub trending AI repositories scraper."""

import logging
import os
from datetime import datetime, timedelta

import httpx

from . import _insert_items

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com/search/repositories"
AI_KEYWORDS = (
    "ai", "artificial-intelligence", "llm", "gpt", "transformer",
    "deep-learning", "machine-learning", "nlp", "neural-network",
    "openai", "langchain", "stable-diffusion", "llama", "rag",
)


def _build_query(since: datetime) -> str:
    """Build a GitHub search query filtered to repos pushed after *since*.

    Uses OR between AI topic keywords so a match on any one term is sufficient.
    """
    since_str = since.strftime("%Y-%m-%d")
    # Use OR so repos matching ANY AI keyword are included, not ALL
    keywords = "+OR+".join(AI_KEYWORDS)
    return f"{keywords}+pushed:>{since_str}"


def _build_headers() -> dict:
    headers = {
        "User-Agent": "ai-news-briefing/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _parse_repo(repo: dict) -> dict | None:
    try:
        return {
            "title": repo["full_name"],
            "url": repo["html_url"],
            "content": repo.get("description") or "",
            "author": repo["owner"]["login"],
            "published_at": datetime.fromisoformat(
                repo["created_at"].replace("Z", "+00:00")
            ),
            "metadata": {
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "language": repo.get("language"),
                "topics": repo.get("topics", []),
                "open_issues": repo.get("open_issues_count", 0),
            },
        }
    except (KeyError, TypeError):
        logger.debug("Skipping malformed GitHub repo item", exc_info=True)
        return None


async def fetch(pool, since: datetime, batch_id) -> int:
    """Fetch trending AI repositories from GitHub and insert into raw_items.

    Returns the number of newly inserted items (0 on failure).
    """
    query = _build_query(since)
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": 10}

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(GITHUB_API, params=params, headers=_build_headers())

            if resp.status_code == 403:
                # Rate-limited — check for retry-after header
                retry_after = resp.headers.get("Retry-After", "unknown")
                logger.warning(
                    "GitHub API rate-limited (Retry-After: %s)", retry_after
                )
                return 0

            if resp.status_code == 422:
                # Usually means the date range has no results or bad query
                logger.warning("GitHub API returned 422 — possibly no repos in window")
                return 0

            resp.raise_for_status()
            data = resp.json()
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        logger.warning("GitHub API request failed: %s", exc)
        return 0
    except Exception:
        logger.exception("Unexpected error fetching GitHub repos")
        return 0

    repos = data.get("items", [])
    items = []
    for repo in repos:
        parsed = _parse_repo(repo)
        if parsed:
            items.append(parsed)

    logger.info("GitHub: %d repos parsed, attempting insert", len(items))
    return await _insert_items(pool, "github", items, batch_id)
