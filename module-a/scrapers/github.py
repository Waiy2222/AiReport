"""GitHub Trending 抓取 — 搜索 AI/Agent 相关仓库"""
import logging
import uuid as uuid_lib
from datetime import datetime, timezone

import httpx

from scrapers.filters import filter_items_by_title

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.github.com/search/repositories"


def build_query(since: datetime) -> str:
    """构造 GitHub 搜索 query：AI/Agent/LLM + 日期过滤"""
    date_str = since.strftime("%Y-%m-%d")
    keywords = ["AI", "Agent", "LLM", "machine learning", "deep learning", "智能体"]
    kw_query = "+".join(keywords)
    return f"{kw_query}+created:>{date_str}"


async def search_repos(since: datetime, per_page: int = 30) -> list[dict]:
    """调 GitHub Search API 获取仓库列表"""
    headers = {"Accept": "application/vnd.github.v3+json"}
    params = {
        "q": build_query(since),
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(SEARCH_URL, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
            return data.get("items", [])
        except Exception as e:
            logger.warning(f"GitHub API failed: {e}")
            return []


def to_raw_items(items: list[dict], batch_id: uuid_lib.UUID) -> list[dict]:
    """将 GitHub API 返回的 repo 列表映射为 raw_items 行"""
    result = []
    for repo in items:
        owner_info = repo.get("owner") or {}
        result.append({
            "source": "github",
            "title": repo.get("full_name", ""),
            "url": repo.get("html_url", ""),
            "content": repo.get("description") or "",
            "author": owner_info.get("login", ""),
            "published_at": _parse_github_time(repo.get("created_at", "")),
            "batch_id": batch_id,
            "metadata": {
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "language": repo.get("language") or "",
                "topics": repo.get("topics", []),
            },
        })
    return result


async def fetch_github(since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """主函数：搜索 → 过滤 → 映射，返回 raw_items 行列表"""
    items = await search_repos(since)
    if not items:
        return []
    ai_items = filter_items_by_title(items, "full_name")
    # 也检查 description
    from scrapers.filters import filter_ai_keywords
    ai_items += [
        i for i in items
        if i not in ai_items and filter_ai_keywords(i.get("description") or "")
    ]
    # 去重（以 full_name 去重）
    seen = set()
    unique = []
    for item in ai_items:
        name = item.get("full_name", "")
        if name not in seen:
            seen.add(name)
            unique.append(item)
    return to_raw_items(unique, batch_id)


def _parse_github_time(time_str: str) -> datetime:
    """解析 GitHub 时间格式到 UTC datetime"""
    if not time_str:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)
