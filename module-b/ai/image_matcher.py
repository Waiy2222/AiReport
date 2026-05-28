"""配图匹配 — 3 级回退：OG 图 → Unsplash → 分类默认"""
import os
import re
import httpx

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")

# ── 分类 → 默认搜索关键词映射 ──
CATEGORY_DEFAULTS = {
    "大模型开源动态": "large language model AI",
    "Agent与智能体框架": "AI agent robot",
    "AI工具链与基础设施": "cloud computing server",
    "AI政策与行业动态": "technology policy government",
    "今日重磅发布": "product launch event",
    "开发者社区热榜": "software developer coding",
    "AI投融资": "startup business investment",
    "LLM": "neural network abstract",
    "Agent": "robot automation",
    "开源": "open source code",
    "推理": "brain neural reasoning",
    "RAG": "database search technology",
    "多模态": "multimedia technology",
    "基础设施": "data center server",
    "融资": "venture capital funding",
    "政策": "government regulation policy",
    "框架": "software framework architecture",
    "工具": "digital tools technology",
    "SDK": "programming code developer",
}


async def _extract_og_image(url: str) -> str | None:
    """Tier 1: 从原文 URL 提取 OG 图片"""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; AiReport/1.0)",
            })
            if resp.status_code != 200:
                return None
            html = resp.text[:50000]  # 只看前 50KB
            match = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html, re.IGNORECASE)
            if not match:
                match = re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', html, re.IGNORECASE)
            if match:
                og_url = match.group(1)
                if og_url.startswith("http"):
                    return og_url
    except Exception:
        pass
    return None


async def _search_unsplash(query: str) -> str | None:
    """Tier 2: 用关键词搜索 Unsplash API"""
    if not UNSPLASH_ACCESS_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    return results[0]["urls"]["regular"]
    except Exception:
        pass
    return None


def _get_category_fallback(item: dict) -> str:
    """Tier 3: 根据分类/标签返回默认配图 URL（使用 Unsplash source 直接 URL）"""
    tags = item.get("tags", [])
    section_title = item.get("_section_title", "")

    keywords = None
    for tag in tags:
        if tag in CATEGORY_DEFAULTS:
            keywords = CATEGORY_DEFAULTS[tag]
            break
    if keywords is None and section_title in CATEGORY_DEFAULTS:
        keywords = CATEGORY_DEFAULTS[section_title]
    if keywords is None:
        keywords = "artificial intelligence technology"

    return f"https://source.unsplash.com/800x400/?{keywords.replace(' ', ',')}"


async def match_image(item: dict) -> str:
    """为单条资讯匹配图片，返回 image_url"""
    url = item.get("url", "")

    # Tier 1: OG 图
    if url:
        og_image = await _extract_og_image(url)
        if og_image:
            return og_image

    # Tier 2: Unsplash 搜索
    keywords = item.get("image_keywords", "")
    if keywords:
        unsplash_url = await _search_unsplash(keywords)
        if unsplash_url:
            return unsplash_url

    # Tier 3: 分类默认
    return _get_category_fallback(item)


async def match_images_for_briefing(briefing: dict) -> dict:
    """为简报中所有 section items 匹配图片，将 image_url 写入每条 item"""
    for section in briefing.get("sections", []):
        section_title = section.get("section_title", "")
        for item in section.get("items", []):
            item["_section_title"] = section_title
            item["image_url"] = await match_image(item)
            item.pop("_section_title", None)
    return briefing
