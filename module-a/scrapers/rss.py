"""RSS 多源并发抓取 — 科技 + 时事 + 国际 + 体育 + 电竞 + 艺术 + 娱乐

v2: ETag条件请求 + UA轮换 + 并发限制 + 多搜索引擎回退
"""
import asyncio
import logging
import random
import re
import uuid as uuid_lib
from calendar import timegm
from datetime import datetime, timezone
from urllib.parse import quote

import feedparser
import httpx

logger = logging.getLogger(__name__)

# ── User-Agent 轮换池（模拟真实浏览器，降低被屏蔽概率）──
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "FeedFetcher/2.0 (compatible; AI-News-Bot/1.0; +https://github.com/ai-news)",
    "RSS-Reader/1.0 (compatible; ai-news-briefing)",
]

# ── ETag/Last-Modified 缓存（避免重复下载未变化的 feed）──
_etag_cache: dict[str, tuple[str | None, str | None]] = {}

# ── 并发限制：防止同时对同一域名发起过多请求 ──
_DOMAIN_SEMAPHORES: dict[str, asyncio.Semaphore] = {}
_MAX_PER_DOMAIN = 4  # 每个域名最多同时4个请求（提升并发）

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
    {"name": "huggingface_blog", "url": "https://huggingface.co/blog/feed.xml", "category": "科技"},

    # ── 时事（中文）──
    {"name": "people",         "url": "http://www.people.com.cn/rss/politics.xml", "category": "时事"},

    # ── 国际（中文）──
    {"name": "bbc_zh",         "url": "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml", "category": "国际"},
    {"name": "voa_zh",         "url": "https://www.voachinese.com/api/",       "category": "国际"},

    # ── 体育 ──
    {"name": "espn",           "url": "https://www.espn.com/espn/rss/news",   "category": "体育"},

    # ── 电竞 / 游戏 ──
    {"name": "dotesports",     "url": "https://dotesports.com/feed",           "category": "体育"},

    # ── 娱乐 / 艺术 / 文化 ──
    {"name": "hollywoodreporter", "url": "https://feeds.feedburner.com/thr/news", "category": "文化艺术"},

    # ── 芯片/半导体 ──
    {"name": "tomshardware",   "url": "https://www.tomshardware.com/feeds/all","category": "芯片"},

    # ── 机器人/自动化 ──
    {"name": "therobotreport", "url": "https://www.therobotreport.com/feed/",  "category": "机器人"},

    # ── 融资/创投 ──
    {"name": "techcrunch",     "url": "https://techcrunch.com/feed/",          "category": "融资"},

    # ── 医疗/健康 ──
    {"name": "sciencedaily_health", "url": "https://www.sciencedaily.com/rss/health_medicine.xml", "category": "医疗"},
    {"name": "news_medical",  "url": "https://www.news-medical.net/syndication.axd?format=rss", "category": "医疗"},
    {"name": "bioworld",      "url": "https://www.bioworld.com/rss.xml",      "category": "医疗"},

    # ── 环保/绿色 ──
    {"name": "greenpeace",    "url": "https://www.greenpeace.org/international/feed/", "category": "环保"},
    {"name": "sciencedaily_env", "url": "https://www.sciencedaily.com/rss/earth_climate.xml", "category": "环保"},
]

# 新闻搜索源 — 多引擎回退（Bing优先→Google→垂直RSS）
NEWS_SEARCH_TEMPLATES = [
    # Tier 1: Bing News RSS（国内更稳定）
    "https://www.bing.com/news/search?q={}&format=rss&cc=cn",
    # Tier 2: Google News CN RSS
    "https://news.google.com/rss/search?q={}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    # Tier 3: Google News EN RSS（兜底）
    "https://news.google.com/rss/search?q={}&hl=en-US&gl=US&ceid=US:en",
]

# ── 个性化简报额外搜索源（化学术/社交媒体/垂直站点）──
# 当常规新闻搜索返回空时，尝试这些垂直源
_VERTICAL_SEARCH = {
    "电竞": [
        "https://www.gosugamers.net/rss/news",
        "https://dotesports.com/feed",
    ],
    "体育": [
        "https://www.espn.com/espn/rss/news",
    ],
    "科技": [
        "https://news.ycombinator.com/rss",
    ],
    "芯片": [
        "https://www.tomshardware.com/feeds/all",
    ],
    "机器人": [
        "https://www.therobotreport.com/feed/",
    ],
    "医疗": [
        "https://www.sciencedaily.com/rss/health_medicine.xml",
        "https://www.news-medical.net/syndication.axd?format=rss",
        "https://www.bioworld.com/rss.xml",
    ],
    "环保": [
        "https://www.sciencedaily.com/rss/earth_climate.xml",
        "https://www.greenpeace.org/international/feed/",
    ],
}


async def fetch_single_rss(source: dict) -> list[dict]:
    """抓取单个 RSS 源 — 带 ETag 条件请求 + UA 轮换 + 域名并发限制"""
    url = source["url"]
    domain = _extract_domain(url)

    # 域名级并发控制
    if domain not in _DOMAIN_SEMAPHORES:
        _DOMAIN_SEMAPHORES[domain] = asyncio.Semaphore(_MAX_PER_DOMAIN)
    sem = _DOMAIN_SEMAPHORES[domain]

    async with sem:
        headers = {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        }
        # ETag/Last-Modified 条件请求（减少带宽60-80%）
        cached_etag, cached_lm = _etag_cache.get(url, (None, None))
        if cached_etag:
            headers["If-None-Match"] = cached_etag
        if cached_lm:
            headers["If-Modified-Since"] = cached_lm

        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)

            if resp.status_code == 304:
                logger.debug(f"RSS [{source['name']}] 304 Not Modified")
                return []  # Feed 未变化，跳过

            if resp.status_code != 200:
                logger.warning(f"RSS [{source['name']}] HTTP {resp.status_code}")
                return []

            # 更新 ETag 缓存
            new_etag = resp.headers.get("ETag")
            new_lm = resp.headers.get("Last-Modified")
            if new_etag or new_lm:
                _etag_cache[url] = (new_etag, new_lm)

            # feedparser 解析（用 run_in_executor 避免阻塞事件循环）
            loop = asyncio.get_running_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, resp.text)

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning(f"RSS [{source['name']}] network error: {e}")
            return []
        except Exception as e:
            logger.warning(f"RSS [{source['name']}] parse error: {e}")
            return []

    if feed.bozo and not feed.entries:
        logger.debug(f"RSS [{source['name']}] bozo: {feed.bozo_exception}")
        return []

    return [
        {**entry, "_source_name": source["name"], "_category": source.get("category", "")}
        for entry in feed.entries
    ]


def _extract_domain(url: str) -> str:
    """从 URL 提取域名（用于并发控制）"""
    import re as _re
    m = _re.match(r'https?://([^/]+)', url)
    return m.group(1) if m else url


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


# 远古时间戳：日期解析失败时返回此值，确保旧条目被 since 过滤掉
# (不能用 datetime.now()，否则旧条目每次都被当作"刚刚发布"，反复出现)
_EPOCH_NAIVE = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_rss_time(entry: dict) -> datetime:
    """解析 RSS 条目的发布时间。失败时返回 epoch 而非 now()，
    确保无法解析日期的旧条目被时效性过滤拦截。"""
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
    # 兜底：返回远古时间，确保被 since 过滤拦截
    logger.debug("RSS time parse failed for entry: %s", entry.get("title", "?")[:60])
    return _EPOCH_NAIVE


# ── 动态关键词新闻搜索（v2: httpx + 多引擎 + 垂直源回退）──
async def search_google_news(keywords: list[str], since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """动态搜索新闻 RSS — 用于个性化简报按用户兴趣实时抓取。

    多级回退策略：
    1. 并发搜索 Google/Bing/DuckDuckGo RSS
    2. 如果某关键词无结果，尝试垂直站点 RSS（电竞/体育/科技等）
    3. 全部失败才返回空
    """
    if not keywords:
        return []

    all_entries: list[dict] = []
    search_sem = asyncio.Semaphore(2)  # 最多2个并发搜索请求（降低防封）

    async def _search_one(kw: str):
        async with search_sem:
            headers = {
                "User-Agent": random.choice(_USER_AGENTS),
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            }
            # 尝试各搜索引擎 RSS
            for template in NEWS_SEARCH_TEMPLATES:
                url = template.format(quote(kw))
                try:
                    async with httpx.AsyncClient(timeout=7.0, follow_redirects=True) as client:
                        resp = await client.get(url, headers=headers)
                    if resp.status_code != 200:
                        continue
                    loop = asyncio.get_running_loop()
                    feed = await loop.run_in_executor(None, feedparser.parse, resp.text)
                    if feed.bozo and not feed.entries:
                        continue
                    if not feed.entries:
                        continue
                    entries = []
                    for entry in feed.entries:
                        entry_time = _entry_time(entry)
                        if entry_time < since:
                            continue
                        entries.append({
                            **entry,
                            "_source_name": "news_search",
                            "_category": "搜索",
                            "_search_keyword": kw,
                        })
                    if entries:
                        all_entries.extend(entries)
                        source_label = "google" if "google" in url else ("bing" if "bing" in url else "other")
                        logger.info(f"News search '{kw}' ({source_label}): {len(entries)} results")
                        return  # 成功
                except Exception as e:
                    logger.debug(f"News search '{kw}' failed for {url[:60]}: {e}")

            # 回退：垂直站点 RSS
            for vert_tag, vert_urls in _VERTICAL_SEARCH.items():
                if vert_tag in kw or kw in vert_tag:
                    for vurl in vert_urls:
                        try:
                            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                                resp = await client.get(vurl, headers=headers)
                            if resp.status_code != 200:
                                continue
                            loop = asyncio.get_running_loop()
                            feed = await loop.run_in_executor(None, feedparser.parse, resp.text)
                            entries = []
                            for entry in feed.entries:
                                if _entry_time(entry) < since:
                                    continue
                                entries.append({
                                    **entry,
                                    "_source_name": "news_search",
                                    "_category": vert_tag,
                                    "_search_keyword": kw,
                                })
                            if entries:
                                all_entries.extend(entries)
                                logger.info(f"Vertical search '{kw}' → {vert_tag}: {len(entries)} results")
                                return
                        except Exception:
                            continue
            logger.warning(f"News search '{kw}': no results from any source")

    # 并发搜索所有关键词
    tasks = [_search_one(kw) for kw in keywords]
    await asyncio.gather(*tasks)

    return to_raw_items(all_entries, "news_search", batch_id)


def _clean_html(text: str) -> str:
    if not text:
        return ""
    # 解码 HTML 实体: &nbsp; &amp; &lt; &#XXXX; 等
    import html
    text = html.unescape(text)
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


async def fetch(pool, since: datetime, batch_id: uuid_lib.UUID) -> list[dict]:
    """Entry point for the scrapers registry — delegates to fetch_rss."""
    return await fetch_rss(since, batch_id)


