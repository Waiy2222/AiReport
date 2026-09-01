"""配图匹配 — 4 级回退：OG 图 → Unsplash+Pexels并发 → 分类默认"""
import asyncio
import os
import re
import httpx

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

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
    # 个性化简报扩展领域
    "电竞": "esports gaming competition",
    "体育": "sports competition stadium",
    "环保": "environmental protection green",
    "文化艺术": "art exhibition gallery",
    "艺术": "art exhibition gallery",
    "音乐": "music concert performance",
    "电影": "movie cinema film",
    "游戏": "video game gaming",
    "教育": "education learning school",
    "能源": "renewable energy green",
    "芯片": "semiconductor chip technology",
    "机器人": "robotics automation",
    "自动驾驶": "autonomous driving car",
    "医疗": "healthcare medical technology",
    "金融": "finance business chart",
    "财经": "finance business chart",
    "国际": "world global news",
    "时事": "world news politics",
}

# ── interest_tags → 英文搜索词（个性化简报用）──
INTEREST_TAG_KEYWORDS = {
    "电竞": "esports gaming competition",
    "体育": "sports competition stadium",
    "环保": "environmental protection green nature",
    "文化艺术": "art exhibition gallery culture",
    "艺术": "art exhibition gallery",
    "音乐": "music concert performance",
    "电影": "movie cinema film",
    "游戏": "video game gaming",
    "教育": "education learning school",
    "能源": "renewable energy green",
    "芯片": "semiconductor chip technology",
    "机器人": "robotics automation",
    "自动驾驶": "autonomous driving car",
    "医疗": "healthcare medical technology",
    "金融": "finance business chart",
    "财经": "finance business chart",
    "融资": "venture capital funding investment",
    "政策": "government policy regulation",
    "国际": "world global news",
    "时事": "world news politics",
    "科技": "technology innovation digital",
    "LLM": "large language model AI neural",
    "Agent": "AI agent robot automation",
    "开源": "open source code github",
    "工具": "developer tools software",
    "安全": "cyber security technology",
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


async def _search_pexels(query: str) -> str | None:
    """Tier 2.5: Pexels API 搜索（国内可访问）"""
    if not PEXELS_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": PEXELS_API_KEY},
            )
            if resp.status_code == 200:
                data = resp.json()
                photos = data.get("photos", [])
                if photos:
                    return photos[0]["src"]["medium"]  # 800px 宽度适合移动端
    except Exception:
        pass
    return None


def _get_fallback_keywords(item: dict) -> str:
    """根据分类/标签返回默认搜索关键词"""
    tags = item.get("tags", [])
    section_title = item.get("_section_title", "")

    for tag in tags:
        if tag in CATEGORY_DEFAULTS:
            return CATEGORY_DEFAULTS[tag]
    if section_title in CATEGORY_DEFAULTS:
        return CATEGORY_DEFAULTS[section_title]
    return "artificial intelligence technology"


async def match_image(item: dict, interest_tags: list[str] | None = None) -> str:
    """为单条资讯匹配图片，返回 image_url

    interest_tags: 个性化简报的兴趣标签，用于生成更相关的搜索词
    """
    url = item.get("url", "")

    # Tier 1: OG 图（跳过，太慢——每条要等3-10秒）
    # og_image = await _extract_og_image(url) if url else None
    # if og_image:
    #     return og_image

    # 获取搜索关键词（item 自身的 + interest_tags 兜底）
    # 优先 _section_tag → _force_tag 确定搜索词
    tag = item.get("_section_tag", "") or item.get("_force_tag", "") or ""
    if tag and tag in INTEREST_TAG_KEYWORDS:
        keywords = INTEREST_TAG_KEYWORDS[tag]
    else:
        keywords = item.get("image_keywords", "")

    # 如果关键词太泛（"technology news"），尝试用 interest_tags 覆盖
    if (not keywords or keywords == "technology news") and interest_tags:
        for tag in interest_tags:
            if tag in INTEREST_TAG_KEYWORDS:
                keywords = INTEREST_TAG_KEYWORDS[tag]
                break

    # Tier 2: Unsplash + Pexels 并发搜索（节省 50% 等待）
    if keywords:
        unsplash_task = asyncio.create_task(_search_unsplash(keywords))
        pexels_task = asyncio.create_task(_search_pexels(keywords))
        unsplash_url = await unsplash_task
        if unsplash_url:
            pexels_task.cancel()
            return unsplash_url
        pexels_url = await pexels_task
        if pexels_url:
            return pexels_url

    # Tier 3: 分类默认（Pexels 兜底）
    fallback_keywords = _get_fallback_keywords(item)
    if fallback_keywords == "artificial intelligence technology" and interest_tags:
        for tag in interest_tags:
            if tag in INTEREST_TAG_KEYWORDS:
                fallback_keywords = INTEREST_TAG_KEYWORDS[tag]
                break
    pexels_fallback = await _search_pexels(fallback_keywords)
    if pexels_fallback:
        return pexels_fallback

    # Tier 4: Unsplash direct URL
    return f"https://source.unsplash.com/800x400/?{fallback_keywords.replace(' ', ',')}"


async def match_images_for_briefing(briefing: dict, interest_tags: list[str] | None = None) -> dict:
    """并发配图：每section首项Pexels API搜图，其余用分类默认图。

    总耗时 <= 5s（并发API请求）。
    """
    tasks = []
    for section in briefing.get("sections", []):
        section_title = section.get("section_title", "")
        items = section.get("items", [])
        for j, item in enumerate(items):
            item["_section_title"] = section_title
            # 把 section 的 tag 传给 item，供配图匹配
            item["_section_tag"] = section.get("tag", "")
            if j == 0:
                # 首项：Pexels API搜图（仅用Pexels，Unsplash挂了）
                tasks.append((item, _search_pexels_by_interest(item, interest_tags)))
            else:
                # 其余：分类默认图
                item["image_url"] = _get_default_image(item, interest_tags)
                item.pop("_section_title", None)

    if not tasks:
        return briefing

    # 并发执行，5s超时
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[t[1] for t in tasks], return_exceptions=True),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        results = [None] * len(tasks)

    for (item, _), url in zip(tasks, results):
        item.pop("_section_title", None)
        if isinstance(url, Exception) or url is None or not url:
            item["image_url"] = _get_default_image(item, interest_tags)
        else:
            item["image_url"] = url

    return briefing


async def _search_pexels_by_interest(item: dict, interest_tags: list[str] | None = None) -> str:
    """用Pexels API搜图（仅Pexels，Unsplash 401/503不可用）"""
    # 优先 _section_tag → _force_tag 确定搜索词
    tag = item.get("_section_tag", "") or item.get("_force_tag", "") or ""
    if tag and tag in INTEREST_TAG_KEYWORDS:
        keywords = INTEREST_TAG_KEYWORDS[tag]
    else:
        keywords = item.get("image_keywords", "")
    if (not keywords or keywords == "technology news") and interest_tags:
        for tag in interest_tags:
            if tag in INTEREST_TAG_KEYWORDS:
                keywords = INTEREST_TAG_KEYWORDS[tag]
                break
    if not keywords:
        keywords = "technology abstract"
    
    api_key = os.getenv("PEXELS_API_KEY", "")
    if not api_key:
        return _get_default_image(item, interest_tags)
    
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://api.pexels.com/v1/search",
                params={"query": keywords, "per_page": 3, "orientation": "landscape"},
                headers={"Authorization": api_key},
            )
            if resp.status_code == 200:
                photos = resp.json().get("photos", [])
                if photos:
                    return photos[0]["src"].get("large") or photos[0]["src"].get("medium", "")
    except Exception:
        pass
    return _get_default_image(item, interest_tags)


def _get_default_image(item: dict, interest_tags: list[str] | None = None) -> str:
    """分类默认图 — 每类多张 Pexels CDN 图轮流使用，避免雷同"""
    # 优先 _section_tag → _force_tag → item tags → 兜底科技
    tag = item.get("_section_tag", "") or item.get("_force_tag", "") or ""
    if not tag:
        tags = item.get("tags") or []
        tag = tags[0] if tags else "科技"
    
    # 每个分类 3-5 张不同图片，按 item title hash 轮换
    defaults = {
        "电竞": [
            "https://images.pexels.com/photos/3165335/pexels-photo-3165335.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/7862536/pexels-photo-7862536.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/7915357/pexels-photo-7915357.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "电子竞技": [
            "https://images.pexels.com/photos/3165335/pexels-photo-3165335.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/7862536/pexels-photo-7862536.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/7915357/pexels-photo-7915357.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "绘画": [
            "https://images.pexels.com/photos/102127/pexels-photo-102127.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/1585325/pexels-photo-1585325.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/1269968/pexels-photo-1269968.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "登山": [
            "https://images.pexels.com/photos/1365425/pexels-photo-1365425.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/1655166/pexels-photo-1655166.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/2416632/pexels-photo-2416632.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "影视": [
            "https://images.pexels.com/photos/33129/popcorn-movie-party-entertainment.jpg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/7991158/pexels-photo-7991158.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/7234221/pexels-photo-7234221.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "音乐": [
            "https://images.pexels.com/photos/1105666/pexels-photo-1105666.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/1763075/pexels-photo-1763075.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/164821/pexels-photo-164821.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/1389429/pexels-photo-1389429.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "咖啡": [
            "https://images.pexels.com/photos/312418/pexels-photo-312418.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/374757/pexels-photo-374757.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/302899/pexels-photo-302899.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "美食": [
            "https://images.pexels.com/photos/958545/pexels-photo-958545.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/842571/pexels-photo-842571.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/1099680/pexels-photo-1099680.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "创业": [
            "https://images.pexels.com/photos/3183150/pexels-photo-3183150.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/3184292/pexels-photo-3184292.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/3861958/pexels-photo-3861958.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "体育": [
            "https://images.pexels.com/photos/248547/pexels-photo-248547.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/114296/pexels-photo-114296.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/159548/pexels-photo-159548.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "汽车": [
            "https://images.pexels.com/photos/170811/pexels-photo-170811.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/337909/pexels-photo-337909.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/244206/pexels-photo-244206.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/919073/pexels-photo-919073.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "环保": [
            "https://images.pexels.com/photos/1072824/pexels-photo-1072824.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/414837/pexels-photo-414837.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/1072821/pexels-photo-1072821.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "LLM": [
            "https://images.pexels.com/photos/18069696/pexels-photo-18069696.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/3861969/pexels-photo-3861969.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/8386440/pexels-photo-8386440.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "Agent": [
            "https://images.pexels.com/photos/8566534/pexels-photo-8566534.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/3861969/pexels-photo-3861969.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/8386440/pexels-photo-8386440.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
        "科技": [
            "https://images.pexels.com/photos/3861969/pexels-photo-3861969.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/8386440/pexels-photo-8386440.jpeg?auto=compress&cs=tinysrgb&w=800",
            "https://images.pexels.com/photos/18069696/pexels-photo-18069696.jpeg?auto=compress&cs=tinysrgb&w=800",
        ],
    }
    
    # 用 item title 的 hash 来选择图片，同一篇文章总是同一张图，不同文章不同图
    title = item.get("title", "")
    idx = sum(ord(c) for c in title) if title else 0
    
    urls = defaults.get(tag, defaults["科技"])
    return urls[idx % len(urls)]
