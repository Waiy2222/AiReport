"""Video clip search and download.

Searches Bilibili (primary), Pexels (free stock footage), and optionally
YouTube for domain-related video clips. Domain is controlled by VIDEO_DOMAIN env var.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path(os.getenv("VIDEO_DOWNLOAD_DIR", "./downloads")).resolve()
SEARCH_SOURCES = os.getenv("VIDEO_SEARCH_SOURCES", "pexels,archive").split(",")
BILIBILI_MAX_DURATION = int(os.getenv("BILIBILI_MAX_DURATION", "600"))  # seconds
BILIBILI_MAX_RESULTS = int(os.getenv("BILIBILI_MAX_RESULTS", "10"))

# Proxy for yt-dlp / httpx (e.g. http://127.0.0.1:7890 for Clash)
_VIDEO_PROXY = os.getenv("VIDEO_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or ""

_VIDEO_DOMAIN_FILTER = os.getenv("VIDEO_DOMAIN", "AI")

# Active domain config injected by pipeline.py at start of each run.
# When set, all domain-aware functions use this instead of env vars / hardcoded maps.
_active_domain_config: dict | None = None


def set_active_domain(domain_key: str, domain_config: dict) -> None:
    """Called by pipeline.py before searching — makes all filters domain-aware.

    After this call, _get_domain_signal_kw, _get_domain_required_kw,
    _is_domain_with_content_gate, and exclusion keyword lists all derive
    from *domain_config* rather than hardcoded tables.
    """
    global _VIDEO_DOMAIN_FILTER, _active_domain_config
    _VIDEO_DOMAIN_FILTER = domain_key
    _active_domain_config = domain_config


# ── Domain-aware keyword sets ──
def _get_domain_signal_kw() -> set[str]:
    """Signal keywords for local cache scoring (domain-specific).

    When _active_domain_config is set (by pipeline), derives keywords from
    the domain config.  Otherwise falls back to built-in presets or env vars.
    """
    if _active_domain_config is not None:
        return _build_signal_from_config(_active_domain_config)

    _MAP: dict[str, set[str]] = {
        "AI": {"ai", "agent", "智能体", "大模型", "科技", "tech", "robot",
               "机器人", "自动驾驶", "coding", "编程", "data", "数据",
               "cloud", "云", "server", "服务", "computing", "计算"},
        "体育": {"体育", "比赛", "联赛", "冠军", "sport", "nba", "足球", "篮球",
                "网球", "f1", "ufc", "赛事", "球员", "球队", "决赛"},
        "芯片": {"芯片", "半导体", "gpu", "cpu", "npu", "nvidia", "intel", "amd",
                "处理器", "算力", "制程", "晶圆", "chip", "台积电"},
        "机器人": {"机器人", "robot", "具身智能", "人形", "机械臂", "自动化",
                  "传感器", "伺服", "boston dynamics", "tesla bot"},
        "医疗": {"医疗", "医学", "药物", "临床", "health", "medical", "诊断",
                "基因", "蛋白质", "疫苗", "手术"},
        "自动驾驶": {"自动驾驶", "self driving", "fsd", "激光雷达", "lidar",
                    "robotaxi", "adas", "智能汽车", "waymo", "tesla"},
        "融资": {"融资", "ipo", "上市", "投资", "估值", "startup", "创投",
                "a轮", "b轮", "天使轮", "收购", "并购"},
    }
    if _VIDEO_DOMAIN_FILTER in _MAP:
        return _MAP[_VIDEO_DOMAIN_FILTER]

    # Dynamic domain: try env var or use domain name as fallback
    raw = os.getenv("VIDEO_DOMAIN_SIGNAL_KW", "")
    if raw:
        return {kw.strip() for kw in raw.split(",") if kw.strip()}
    return {_VIDEO_DOMAIN_FILTER}


def _build_signal_from_config(dc: dict) -> set[str]:
    """Derive signal keywords from a domain config dict."""
    import re as _re
    kw: set[str] = set()
    kw.add(dc["label"].lower())
    kw.add(dc["display"].lower())
    # From broll_fallback
    for w in dc.get("broll_fallback", "").split():
        w = w.strip().lower()
        if w and len(w) >= 2:
            kw.add(w)
    # From prompt_context
    for part in _re.split(r'[、，,；;。.\s]+', dc.get("prompt_context", "")):
        part = part.strip().lower()
        if part and len(part) >= 2:
            kw.add(part)
    # From en_to_cn values (Chinese keywords are most useful for B站/local cache)
    for cn in dc.get("en_to_cn", {}).values():
        if cn and len(cn) >= 2:
            kw.add(cn.lower())
    return kw


def _get_domain_required_kw() -> list[str]:
    """Required keywords for domain relevance gate on B站 results.

    When _active_domain_config is set, derives from domain config.
    Otherwise falls back to built-in presets or env vars.
    """
    if _active_domain_config is not None:
        return _build_required_from_config(_active_domain_config)

    _MAP: dict[str, list[str]] = {
        "AI": [
            "AI", "人工智能", "智能", "科技", "技术", "数字", "数据", "计算",
            "芯片", "半导体", "处理器", "算力", "GPU", "CPU", "NPU",
            "大模型", "语言模型", "深度学习", "机器学习", "神经网络",
            "智能体", "Agent", "agent", "机器人", "自动化", "编程", "代码",
            "开源", "软件", "系统", "平台", "云", "服务器",
            "腾讯", "阿里", "百度", "华为", "字节", "小米", "京东", "美团",
            "OpenAI", "DeepSeek", "NVIDIA", "英伟达", "Google", "谷歌", "Microsoft", "微软",
            "GPT", "Claude", "Gemini", "LLM", "LLaMA",
            "自动驾驶", "新能源", "电动车", "特斯拉",
            "发布", "融资", "上市", "投资", "收购",
        ],
        "体育": [
            "体育", "比赛", "联赛", "冠军", "NBA", "足球", "篮球", "网球",
            "赛事", "球队", "球员", "决赛", "半决赛", "F1", "UFC",
            "英超", "西甲", "欧冠", "世界杯", "奥运会", "中超",
            "转会", "比分", "进球", "夺冠",
        ],
        "芯片": [
            "芯片", "半导体", "处理器", "GPU", "CPU", "NPU", "算力",
            "NVIDIA", "英伟达", "Intel", "英特尔", "AMD", "台积电",
            "晶圆", "制程", "架构", "HBM", "高带宽", "AI芯片",
        ],
        "机器人": [
            "机器人", "人形机器人", "具身智能", "机械臂", "自动化",
            "Robot", "robotics", "波士顿动力", "Tesla Bot",
            "传感器", "伺服电机", "ROS", "运动控制",
        ],
        "医疗": [
            "医疗", "医学", "药物", "临床", "FDA", "新药", "治疗",
            "诊断", "基因", "蛋白质", "疫苗", "手术", "医疗器械",
        ],
        "自动驾驶": [
            "自动驾驶", "FSD", "激光雷达", "Lidar", "Robotaxi", "智能汽车",
            "ADAS", "Waymo", "Tesla", "车路协同", "无人驾驶", "传感器",
        ],
        "融资": [
            "融资", "IPO", "上市", "投资", "估值", "收购", "并购",
            "A轮", "B轮", "天使轮", "独角兽", "创投", "Startup",
        ],
    }
    if _VIDEO_DOMAIN_FILTER in _MAP:
        return _MAP[_VIDEO_DOMAIN_FILTER]

    # Dynamic domain: try env var or use domain name as fallback
    raw = os.getenv("VIDEO_DOMAIN_REQUIRED_KW", "")
    if raw:
        return [kw.strip() for kw in raw.split(",") if kw.strip()]
    return [_VIDEO_DOMAIN_FILTER]


def _build_required_from_config(dc: dict) -> list[str]:
    """Derive required keywords from a domain config dict."""
    import re as _re
    kw: list[str] = []
    kw.append(dc["label"])
    kw.append(dc["display"])
    # From broll_fallback
    for w in dc.get("broll_fallback", "").split():
        w = w.strip()
        if w and len(w) >= 2:
            kw.append(w)
    # From prompt_context
    for part in _re.split(r'[、，,；;。.\s]+', dc.get("prompt_context", "")):
        part = part.strip()
        if part and len(part) >= 2:
            kw.append(part)
    # From en_to_cn values
    for cn in dc.get("en_to_cn", {}).values():
        if cn and len(cn) >= 2:
            kw.append(cn)
    return kw


def _is_domain_with_content_gate() -> bool:
    """Whether to apply strict content gate (tech/non-tech filtering).

    When _active_domain_config is set, gate is ON only for tech-heavy domains.
    Non-tech domains (体育, 医疗, 融资, custom keywords) skip content gating.
    Otherwise falls back to hardcoded list + env var.
    """
    if _active_domain_config is not None:
        # Content gate only for domains where non-tech junk is a real problem.
        # Sports / medical / finance / custom keywords → no gate (let the
        # relevance scorer do its job with domain-specific context).
        _TECH_DOMAINS = {"AI", "科技", "芯片", "机器人", "自动驾驶"}
        return _VIDEO_DOMAIN_FILTER in _TECH_DOMAINS

    if _VIDEO_DOMAIN_FILTER in ("AI", "科技", "芯片", "机器人", "自动驾驶"):
        return True
    return os.getenv("VIDEO_DOMAIN_CONTENT_GATE", "").lower() in ("1", "true", "yes")
# ── BROAD irrelevant categories: food, sports, entertainment, travel, etc. ──
# Only applied when _is_domain_with_content_gate() is True (tech domains).
# For sports/medical/custom domains, these are NOT excluded — the relevance
# scorer handles filtering with domain-specific context instead.
_NON_TECH_EXCLUDE_KW_RAW = [
    # Food & beverage
    "啤酒", "白酒", "红酒", "饮料", "美食", "烹饪", "餐厅", "外卖",
    "火锅", "烧烤", "奶茶", "咖啡", "零食", "小吃", "茅台",
    # Sports
    "足球", "篮球", "NBA", "英超", "中超", "世界杯", "奥运会",
    "跑步", "健身", "瑜伽", "马拉松",
    # Entertainment
    "综艺", "明星", "演员", "歌手", "电视剧", "电影", "综艺节目",
    "娱乐", "八卦", "网红",
    # Travel & lifestyle
    "旅游", "景点", "酒店", "民宿", "拍照", "打卡",
    "穿搭", "美妆", "护肤", "发型",
    # Cars (non-EV)
    "汽车测评", "二手车", "改装",
]


def _get_non_tech_exclude() -> list[str]:
    """Return non-tech exclusion keywords only when content gate is enabled.

    For non-tech domains (体育/医疗/custom keywords), returns empty list —
    the relevance scorer handles filtering with domain-specific context.
    """
    if not _is_domain_with_content_gate():
        return []
    return _NON_TECH_EXCLUDE_KW_RAW


# Game-related keywords to EXCLUDE from B-roll results entirely
# Only applied when _is_domain_with_content_gate() is True.
_GAME_EXCLUDE_KW_RAW = [
    "游戏", "电竞", "王者荣耀", "英雄联盟", "原神", "崩坏", "星穹铁道",
    "明日方舟", "我的世界", "吃鸡", "绝地求生", "赛博朋克", "魔兽世界",
    "魔兽", "梦幻西游", "地下城", "和平精英", "蛋仔派对", "第五人格",
    "阴阳师", "光遇", "永劫无间", "守望先锋", "炉石传说", "怪物猎人",
    "最终幻想", "剑网", "逆水寒", "天龙八部", "征途", "迷你世界",
    "暗黑破坏神", "使命召唤", "穿越火线", "CF", "生死狙击", "全民枪战",
    "部落冲突", "皇室战争", "荒野乱斗", "宝可梦", "精灵宝可梦",
    "Minecraft", "LOL", "PUBG", "DNF", "WOW", "Genshin", "Honkai",
]


def _get_game_exclude() -> list[str]:
    """Return game exclusion keywords only when content gate is enabled."""
    if not _is_domain_with_content_gate():
        return []
    return _GAME_EXCLUDE_KW_RAW

# Advertising / commercial / scam keywords to EXCLUDE entirely
# These catch "智能体课程退费" style ads disguised as tech content
_AD_EXCLUDE_KW = [
    # 课程/培训/教育类广告
    "课程", "培训", "退费", "退款", "报名", "试听", "网课", "线上课",
    "线下课", "培训班", "训练营", "速成班", "考证", "学历", "专升本",
    "自考", "成考", "考研班", "四六级", "雅思", "托福", "GRE",
    # 营销/推广/赚钱
    "广告", "推广", "营销", "引流", "涨粉", "吸粉", "带货", "直播带货",
    "赚钱", "副业", "月入", "年入", "暴富", "躺赚", "薅羊毛", "返利",
    "优惠券", "满减", "限时抢购", "秒杀", "拼团", "砍价", "免单",
    # 理财/投资/股票
    "理财", "炒股", "荐股", "涨停", "跌停", "私募", "期货", "外汇",
    "虚拟币", "挖矿", "区块链投资", "币圈", "比特币", "以太坊",
    "资金盘", "传销", "庞氏", "加盟", "代理", "招商",
    # 医疗/保健
    "减肥", "瘦身", "丰胸", "增高", "补肾", "壮阳", "脱发", "植发",
    # 情感/婚恋/其他
    "征婚", "相亲平台", "挽回", "复合", "算命", "风水", "星座运势",
    # 卖课/知识付费特征（非技术分享）
    "限时优惠", "最后一天", "名额有限", "先到先得", "早鸟价", "拼团价",
    "试听课", "体验课", "公开课报名", "扫码入群", "加微信", "私信领取",
]


class VideoSearcher:
    """Search and download video clips from the web."""

    PEXELS_BASE = "https://api.pexels.com/videos"

    @staticmethod
    async def _run_subprocess(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a subprocess in a thread to avoid blocking the asyncio event loop."""
        import concurrent.futures
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=timeout, encoding="utf-8", errors="replace"),
        )

    def __init__(self):
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self._local_cache: list[dict] | None = None

    async def _build_local_cache(self) -> list[dict]:
        """Scan downloads folder for ALL previously downloaded clips.

        Indexes both bilibili_*.mp4 (YouTube/B站 with yt-dlp metadata) AND
        Pexels numeric-name files (via ffprobe for duration).  This ensures
        the full 2.6GB+ cache of previously downloaded material is reusable.
        """
        if self._local_cache is not None:
            return self._local_cache
        cache: list[dict] = []
        import json as _json

        all_mp4 = sorted(DOWNLOAD_DIR.glob("*.mp4"))

        for f in all_mp4[:50]:  # Cap at 50 files (older ones unlikely to be reused)
            try:
                is_bili = f.name.startswith("bilibili_")
                # Use ffprobe for ALL files — yt-dlp is too slow for cache building
                probe = await self._run_subprocess(
                    ["ffprobe", "-v", "quiet", "-print_format", "json",
                     "-show_format", str(f)], timeout=8)
                if probe.returncode == 0 and probe.stdout.strip():
                    info = _json.loads(probe.stdout.strip())
                    fmt = info.get("format", {})
                    dur = float(fmt.get("duration", 30) or 30)
                    tags = fmt.get("tags", {})
                    title = tags.get("title", "") or f.stem
                    platform = "youtube" if is_bili else "pexels"
                    cache.append({
                        "title": title,
                        "url": "file://" + str(f),
                        "file_path": str(f),
                        "duration_sec": min(dur, 300),
                        "platform": platform,
                        "description": tags.get("comment", "") or "",
                        "view_count": 0,
                        "thumbnail": "",
                        "is_tutorial": False,
                        "is_subtitles": False,
                    })
            except Exception:
                pass

        logger.info("Local cache: %d clips", len(cache))
        self._local_cache = cache
        return cache

    async def _search_local_cache(self, query: str, max_results: int) -> list[dict]:
        """Match query against locally cached downloads — Chinese + English aware.

        Uses multi-level scoring:
        - Chinese character n-gram overlapping (2-4 char chunks)
        - English keyword substring matching
        - Entity/company name bonus
        """
        cache = await self._build_local_cache()
        if not cache:
            return []
        query_lower = query.lower()
        results = []

        # Extract Chinese tokens from query (2-4 char n-grams)
        cn_chunks: list[str] = []
        for n in (4, 3, 2):
            for i in range(len(query) - n + 1):
                chunk = query[i:i + n]
                if all('一' <= c <= '鿿' for c in chunk):
                    cn_chunks.append(chunk)
        # Dedup preserving order
        seen = set()
        cn_chunks = [c for c in cn_chunks if not (c in seen or seen.add(c))]

        for clip in cache:
            title = (clip.get("title", "") or "")
            desc = (clip.get("description", "") or "")
            content = (title + " " + desc).lower()
            score = 0

            # Level 1: Chinese n-gram matching (2-4 char)
            for chunk in cn_chunks:
                if chunk in content or chunk in title:
                    chunk_len = len(chunk)
                    if chunk_len >= 4:
                        score += 12  # 4-char match = strong signal
                    elif chunk_len == 3:
                        score += 6
                    else:
                        score += 2

            # Level 2: English keyword matching
            for kw in query_lower.split():
                kw_clean = kw.strip('，。、；：？！,.!?;:')
                if len(kw_clean) >= 3 and kw_clean in content:
                    score += 5
                elif len(kw_clean) >= 2 and kw_clean in content:
                    score += 2

            # Level 3: domain signal bonus
            _SIGNAL_KW = _get_domain_signal_kw()
            signal_hits = sum(1 for t in _SIGNAL_KW if t in content)
            score += signal_hits * 3

            if score > 0:
                clip["_local_score"] = score
                results.append(clip)

        results.sort(key=lambda r: r.get("_local_score", 0), reverse=True)
        logger.info("Local cache search '%s': %d results (top score=%d)",
                    query[:50], len(results), results[0].get("_local_score", 0) if results else 0)
        return results[:max_results]

    async def search(
        self,
        query: str,
        max_results: int = 10,
        min_duration_sec: int = 10,
        max_duration_sec: int = 300,
    ) -> list[dict[str, Any]]:
        """Search for video clips matching a query.

        Local cache first, then Pexels, YouTube, B站, Archive.org.
        """
        # 1. Local cache — instant, no network, high relevance
        local_results = await self._search_local_cache(query, max_results)
        if len(local_results) >= max_results:
            return local_results[:max_results]

        # ── Launch all sources CONCURRENTLY, each with its own timeout ──
        # Use asyncio.gather with individual wait_for wrappers. Each source
        # gets a firm timeout; TimeoutError is caught and converted to [].
        source_set = {s.strip() for s in SEARCH_SOURCES}

        async def _with_timeout(coro, timeout: float, label: str) -> list[dict]:
            try:
                return await asyncio.wait_for(coro, timeout=timeout)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug("Source %s: %s after %.0fs", label, type(e).__name__, timeout)
                return []

        tasks = []
        if "pexels" in source_set:
            tasks.append(_with_timeout(
                self._search_pexels(query, max_results, min_duration_sec, max_duration_sec),
                12, "pexels"))
        else:
            tasks.append(asyncio.sleep(0, result=[]))  # dummy, instant

        if "bilibili" in source_set:
            tasks.append(_with_timeout(
                self._search_bilibili(query, max_results),
                15, "bilibili"))
        else:
            tasks.append(asyncio.sleep(0, result=[]))

        if "youtube" in source_set:
            tasks.append(_with_timeout(
                self._search_youtube(query, max_results, min_duration_sec, max_duration_sec),
                18, "youtube"))
        else:
            tasks.append(asyncio.sleep(0, result=[]))

        if "archive" in source_set:
            tasks.append(_with_timeout(
                self._search_archive(query, max_results, min_duration_sec, max_duration_sec),
                12, "archive"))
        else:
            tasks.append(asyncio.sleep(0, result=[]))

        gathered = await asyncio.gather(*tasks)
        pexels_results, bili_raw, yt_raw, archive_results = gathered

        bili_raw = bili_raw if isinstance(bili_raw, list) else []
        bili_clean: list[dict] = []
        bili_tutorial: list[dict] = []
        for v in bili_raw:
            if v.get("is_tutorial"):
                bili_tutorial.append(v)
            else:
                bili_clean.append(v)

        yt_raw = yt_raw if isinstance(yt_raw, list) else []
        youtube_clean: list[dict] = []
        youtube_tutorial: list[dict] = []
        for v in yt_raw:
            if v.get("is_tutorial"):
                youtube_tutorial.append(v)
            else:
                youtube_clean.append(v)

        archive_results = archive_results if isinstance(archive_results, list) else []
        pexels_results = pexels_results if isinstance(pexels_results, list) else []

        # Priority: Local cache → YouTube → B站 → tutorials → Pexels → Archive
        results = (local_results + youtube_clean + bili_clean +
                   youtube_tutorial + bili_tutorial + pexels_results +
                   archive_results)

        logger.info("Video search for '%s': %d results (YouTube:%d B站:%d Pexels:%d Archive:%d)",
                    query, len(results),
                    len(youtube_clean) + len(youtube_tutorial),
                    len(bili_clean) + len(bili_tutorial),
                    len(pexels_results), len(archive_results))
        return results

    async def download(
        self,
        video_url: str,
        start_sec: float = 0,
        end_sec: float | None = None,
    ) -> str | None:
        """Download a video clip and return local file path.

        Uses yt-dlp for B站/YouTube, httpx for direct (Pexels) URLs.
        """
        # Local file — just return the path
        if video_url.startswith("file://"):
            return video_url[7:]

        # B站 / YouTube — use yt-dlp
        if "bilibili.com" in video_url or "youtube.com" in video_url or "youtu.be" in video_url:
            return await self._download_ytdlp(video_url, start_sec, end_sec)

        # Pexels / direct URLs — httpx download with retry
        import asyncio as _asyncio
        last_error = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=120, proxy=_VIDEO_PROXY or None) as client:
                    resp = await client.get(video_url)
                    if resp.status_code == 200:
                        filename = Path(video_url).name or f"clip_{hash(video_url)}.mp4"
                        out_path = str(DOWNLOAD_DIR / filename)
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        logger.info("Downloaded: %s -> %s (attempt %d)", video_url, out_path, attempt + 1)
                        return out_path
                    else:
                        logger.warning("Download HTTP %d for %s (attempt %d)", resp.status_code, video_url, attempt + 1)
            except Exception as e:
                last_error = e
                logger.warning("Download attempt %d failed for %s: %s", attempt + 1, video_url, e)
            if attempt < 2:
                await _asyncio.sleep(1 + attempt * 1.5)  # 1s, 2.5s

        if last_error:
            logger.warning("Download failed after 3 attempts: %s", video_url)
        return None

    async def _download_ytdlp(
        self,
        video_url: str,
        start_sec: float = 0,
        end_sec: float | None = None,
    ) -> str | None:
        """Download a video via yt-dlp (B站/YouTube). Retries up to 5 times for 412."""
        import uuid as _uuid
        import asyncio as _asyncio

        video_id = _uuid.uuid4().hex[:8]
        out_template = str(DOWNLOAD_DIR / f"bilibili_{video_id}.%(ext)s")

        cmd_base = [
            "yt-dlp",
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "-o", out_template,
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--socket-timeout", "30",
            "--retries", "5",
            "--fragment-retries", "5",
            "--extractor-retries", "5",
        ]
        if _VIDEO_PROXY:
            cmd_base += ["--proxy", _VIDEO_PROXY]

        # Download a segment if specified
        if end_sec is not None and end_sec > start_sec:
            cmd_base += ["--download-sections", f"*{start_sec}-{end_sec}"]

        last_error = None
        for attempt in range(2):  # Reduced from 5 — B站 412 is persistent, fail fast
            cmd = cmd_base + [video_url]
            try:
                result = await self._run_subprocess(cmd, timeout=30)
                if result.returncode == 0:
                    # Find the output file
                    out_mp4 = str(DOWNLOAD_DIR / f"bilibili_{video_id}.mp4")
                    if Path(out_mp4).exists():
                        logger.info("Downloaded (yt-dlp): %s -> %s (attempt %d)", video_url, out_mp4, attempt + 1)
                        return out_mp4
                    for f in DOWNLOAD_DIR.glob(f"bilibili_{video_id}.*"):
                        logger.info("Downloaded (yt-dlp): %s -> %s (attempt %d)", video_url, str(f), attempt + 1)
                        return str(f)
                    logger.warning("yt-dlp output file not found for %s", video_url)
                    return None

                stderr_tail = (result.stderr or "")[-300:]
                if "412" in stderr_tail or "Precondition Failed" in stderr_tail:
                    wait = 3 + attempt * 3  # 3s, 6s, 9s, 12s, 15s
                    logger.info("yt-dlp 412 (attempt %d/5), waiting %ds...", attempt + 1, wait)
                    await _asyncio.sleep(wait)
                    continue
                else:
                    logger.warning("yt-dlp failed: %s", stderr_tail)
                    return None

            except subprocess.TimeoutExpired:
                logger.warning("yt-dlp download timed out: %s (attempt %d)", video_url, attempt + 1)
                last_error = "timeout"
                if attempt < 4:
                    await _asyncio.sleep(3)
            except FileNotFoundError:
                logger.error("yt-dlp not found. Run: pip install yt-dlp")
                return None
            except Exception as e:
                last_error = str(e)
                logger.warning("yt-dlp exception (attempt %d): %s", attempt + 1, e)
                if attempt < 4:
                    await _asyncio.sleep(2)

        logger.warning("yt-dlp download failed after 2 attempts: %s", video_url)
        return None

    # ---- Archive.org -------------------------------------------------------

    async def _search_archive(
        self,
        query: str,
        max_results: int,
        min_dur: int,
        max_dur: int,
    ) -> list[dict[str, Any]]:
        """Search Archive.org for video clips (best-effort, requires network)."""
        try:
            import urllib.parse
            en_query = _to_pexels_query(query)
            search_url = (
                f"https://archive.org/advancedsearch.php"
                f"?q={urllib.parse.quote(en_query)}+AND+mediatype:movies"
                f"&fl[]=identifier,title,description&rows={min(max_results, 10)}"
                f"&output=json"
            )
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(search_url)
                if resp.status_code != 200:
                    return []
                data = resp.json()
            docs = data.get("response", {}).get("docs", [])
            results = []
            for doc in docs:
                identifier = doc.get("identifier", "")
                if not identifier:
                    continue
                results.append({
                    "title": doc.get("title", "") or identifier,
                    "url": f"https://archive.org/download/{identifier}/{identifier}.mp4",
                    "duration_sec": min(max_dur, 120),
                    "platform": "archive",
                    "description": (doc.get("description", "") or "")[:300],
                    "thumbnail": f"https://archive.org/services/img/{identifier}",
                    "view_count": 0,
                })
            logger.info("Archive.org search: %d results for '%s'", len(results), query[:50])
            return results[:max_results]
        except Exception:
            logger.debug("Archive.org search failed for '%s'", query[:50])
            return []

    # ---- Pexels Photos (images for Ken Burns B-roll) -----------------------

    PEXELS_PHOTOS_BASE = "https://api.pexels.com/v1"

    async def _search_unsplash_images(self, query: str, max_results: int = 5) -> list[dict]:
        """Search Unsplash for photos (free, no auth).

        NOTE: Unsplash NAPI is unreliable (frequent 403). This is a best-effort
        supplementary source — failures are silent.
        """
        try:
            en_query = _to_pexels_query(query)
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://unsplash.com/napi/search/photos",
                    params={"query": en_query, "per_page": min(max_results, 10),
                            "orientation": "landscape"},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Referer": "https://unsplash.com/",
                        "Accept": "application/json",
                    },
                )
                if resp.status_code != 200:
                    return []  # 403/429 common — silently skip
                data = resp.json()
                results = []
                for p in data.get("results", []):
                    urls = p.get("urls", {})
                    img_url = urls.get("regular") or urls.get("small") or ""
                    if not img_url:
                        continue
                    results.append({
                        "title": p.get("alt_description", "") or p.get("description", "") or query,
                        "url": img_url,
                        "duration_sec": 5,
                        "platform": "unsplash",
                        "type": "image",
                        "description": f"Photo by {p.get('user', {}).get('name', '')}",
                        "thumbnail": urls.get("thumb", ""),
                        "width": p.get("width", 0),
                        "height": p.get("height", 0),
                    })
                logger.info("Unsplash Photo search: %d results for '%s'", len(results), query)
                return results[:max_results]
        except Exception as e:
            logger.debug("Unsplash search failed: %s", e)
            return []

    async def _search_wikimedia_images(self, query: str, max_results: int = 5) -> list[dict]:
        """Search Wikimedia Commons for freely-licensed images.

        Zero-config: no API key, no auth.  Provides unique content that
        stock photo sites lack — real product photos, company logos,
        chip close-ups, tech hardware, historical footage.
        """
        try:
            # Lazy import — only load when called
            from tools.search.wikimedia import WikimediaSearcher

            # Wikimedia works best with English queries + entity names
            en_query = _to_pexels_query(query)
            searcher = WikimediaSearcher()
            try:
                results = await searcher.search_images(en_query, max_results=max_results)
            finally:
                await searcher.close()
            logger.info("Wikimedia: %d images for '%s'", len(results), query[:50])
            return results
        except Exception as e:
            logger.debug("Wikimedia search failed: %s", e)
            return []

    async def _search_bilibili_covers(self, query: str, max_results: int = 6) -> list[dict]:
        """Search B站 for video covers — great Chinese-relevant image source."""
        try:
            r = await self._search_bilibili(query, max_results)
            results = []
            for v in r:
                thumb = v.get("thumbnail", "")
                if not thumb:
                    continue
                title = v.get("title", "") or ""
                desc = v.get("description", "") or ""
                results.append({
                    "title": title,
                    "url": thumb,
                    "platform": "bilibili_cover",
                    "type": "image",
                    "description": desc,
                    "duration_sec": v.get("duration_sec", 5),
                })
            return results
        except Exception:
            return []

    async def search_images(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Search multiple sources for relevant photos for Ken Burns B-roll.

        Sources (in priority order):
        1. Pexels Photos API (needs PEXELS_API_KEY)
        2. Wikimedia Commons (free, no key — logos, products, tech diagrams)
        3. Unsplash (free, no auth)

        Returns a list of dicts with keys: title, url (direct image link),
        platform, type='image', thumbnail, width, height.
        """
        # Source 1: Pexels (stock photos, needs API key)
        api_key = os.getenv("PEXELS_API_KEY", "")
        pexels_results: list[dict] = []
        if api_key:
            pexels_query = _to_pexels_query(query)

            try:
                async with httpx.AsyncClient(timeout=30, proxy=_VIDEO_PROXY or None) as client:
                    resp = await client.get(
                        f"{self.PEXELS_PHOTOS_BASE}/search",
                        params={
                            "query": pexels_query,
                            "per_page": min(max_results, 15),
                            "orientation": "landscape",
                            "size": "large",
                        },
                        headers={"Authorization": api_key},
                    )
                    if resp.status_code != 200:
                        logger.warning("Pexels Photos API error %d: %s", resp.status_code, resp.text[:200])
                    else:
                        data = resp.json()
                        photos = data.get("photos", [])

                        for p in photos:
                            src = p.get("src", {})
                            image_url = src.get("original") or src.get("large2x") or src.get("large") or ""
                            if not image_url:
                                continue
                            alt = p.get("alt", "") or ""
                            photographer = p.get("photographer", "")
                            pexels_results.append({
                                "title": alt or pexels_query,
                                "url": image_url,
                                "duration_sec": 5,
                                "platform": "pexels_photo",
                                "type": "image",
                                "description": f"Photo by {photographer}" if photographer else "",
                                "thumbnail": src.get("medium", ""),
                                "width": p.get("width", 0),
                                "height": p.get("height", 0),
                                "photographer": photographer,
                            })

                logger.info("Pexels Photo search: %d results for '%s' (query: '%s')",
                            len(pexels_results), query, pexels_query)
            except Exception as e:
                logger.warning("Pexels Photo search failed: %s", e)

        # Source 2: Wikimedia Commons (free, no auth — logos, real product photos)
        wikimedia_results = await self._search_wikimedia_images(query, max_results)

        # Source 3: Unsplash (free, no auth)
        unsplash_results = await self._search_unsplash_images(query, max_results)

        # Merge: interleave Pexels + Wikimedia + Unsplash for source diversity.
        # Don't let any single source dominate — Wikimedia provides unique
        # real-world tech imagery (logos, chips, hardware) that stock sites lack.
        seen_urls: set[str] = set()
        all_results: list[dict] = []
        # Round-robin: pick from each source in turn
        sources = [pexels_results, wikimedia_results, unsplash_results]
        indices = [0, 0, 0]
        while len(all_results) < max_results:
            added = False
            for si, src in enumerate(sources):
                if indices[si] < len(src):
                    r = src[indices[si]]
                    indices[si] += 1
                    if r["url"] not in seen_urls:
                        seen_urls.add(r["url"])
                        all_results.append(r)
                        added = True
                        if len(all_results) >= max_results:
                            break
            if not added:
                break  # all sources exhausted
        return all_results[:max_results]

    async def download_image(self, image_url: str) -> str | None:
        """Download an image from a direct URL to the downloads directory.

        Retries up to 3 times with backoff.  Returns the local file path,
        or None if all attempts fail.
        """
        import asyncio as _asyncio

        # Fix protocol-relative URLs (e.g. //i2.hdslb.com/...)
        if image_url.startswith("//"):
            image_url = "https:" + image_url

        last_error = None
        for attempt in range(3):
            try:
                # Determine file extension from URL or Content-Type
                async with httpx.AsyncClient(timeout=60, proxy=_VIDEO_PROXY or None) as client:
                    resp = await client.get(image_url)
                    if resp.status_code == 200:
                        # Use extension from URL or default to .jpg
                        url_path = Path(image_url.split("?")[0])
                        ext = url_path.suffix if url_path.suffix in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
                        filename = f"pexels_img_{hash(image_url) & 0xFFFFFF:06x}{ext}"
                        out_path = str(DOWNLOAD_DIR / filename)
                        with open(out_path, "wb") as f:
                            f.write(resp.content)
                        logger.info("Downloaded image: %s → %s (%.1f KB, attempt %d)",
                                    image_url[:80], out_path, len(resp.content) / 1024, attempt + 1)
                        return out_path
                    else:
                        logger.warning("Image download HTTP %d for %s (attempt %d)",
                                       resp.status_code, image_url[:80], attempt + 1)
            except Exception as e:
                last_error = e
                logger.warning("Image download attempt %d failed: %s", attempt + 1, e)
            if attempt < 2:
                await _asyncio.sleep(1 + attempt * 1.5)

        if last_error:
            logger.warning("Image download failed after 3 attempts: %s", image_url[:80])
        return None

    async def search_by_preferences(
        self,
        user_tags: list[str],
        briefing_topics: list[str],
        max_results: int = 15,
    ) -> list[dict[str, Any]]:
        """Build search queries from user preferences and briefing topics."""
        all_queries = set(user_tags + briefing_topics)
        all_queries.discard("")

        all_results: list[dict] = []
        seen_urls: set[str] = set()

        for q in list(all_queries)[:5]:
            results = await self.search(f"AI {q}", max_results=5)
            for r in results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    all_results.append(r)
            if len(all_results) >= max_results:
                break

        return all_results[:max_results]

    # ---- Bilibili ---------------------------------------------------------

    async def _search_bilibili(
        self, query: str, max_results: int = 10
    ) -> list[dict[str, Any]]:
        """Search B站 via public API, then enrich with yt-dlp metadata.

        Uses B站's public search API (no auth needed), then fetches
        full metadata (duration, etc.) via yt-dlp --skip-download.
        """
        import json as _json
        import urllib.parse

        try:
            # Step 1: Search via B站 public API
            encoded_query = urllib.parse.quote(query)
            search_url = (
                f"https://api.bilibili.com/x/web-interface/search/type"
                f"?search_type=video&keyword={encoded_query}"
                f"&page=1&page_size={min(max_results, 20)}"
            )

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.bilibili.com/",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }

            import asyncio as _asyncio
            async with httpx.AsyncClient(timeout=30, proxy=_VIDEO_PROXY or None) as client:
                resp = await client.get(search_url, headers=headers)
                # Retry once for 412 rate limiting (B站 is unreliable, fail fast)
                retry = 0
                while resp.status_code == 412 and retry < 1:
                    wait = 2
                    logger.info("B站 412 (attempt %d), waiting %ds...", retry + 1, wait)
                    await _asyncio.sleep(wait)
                    resp = await client.get(search_url, headers=headers)
                    retry += 1
                if resp.status_code != 200:
                    logger.warning("B站 API returned %d after %d retries", resp.status_code, retry)
                    return []

                data = resp.json()
                if data.get("code") != 0:
                    logger.warning("B站 API error: %s", data.get("message", ""))
                    return []

            video_list = data.get("data", {}).get("result", [])
            if not video_list:
                logger.info("B站 search: 0 results for '%s'", query)
                return []

            # Step 2: Enrich with full metadata via yt-dlp --skip-download
            import re as _re

            # Tutorial keywords that indicate hard-coded Chinese subtitles
            _TUTORIAL_KW = ["教程", "课程", "合集", "教学", "讲解",
                           "入门", "速成", "零基础", "学习", "课堂",
                           "面试", "刷题", "真题", "考点", "复习"]

            results: list[dict] = []
            for v in video_list[:max_results]:
                bvid = v.get("bvid", "")
                aid = v.get("aid", 0)
                url = f"https://www.bilibili.com/video/{bvid}" if bvid else (
                    f"https://www.bilibili.com/video/av{aid}" if aid else ""
                )

                if not url:
                    continue

                # Basic info from API
                title = v.get("title", "")
                title = _re.sub(r"<[^>]+>", "", title)
                api_duration = v.get("duration", "")
                duration_sec = 120
                if api_duration and ":" in api_duration:
                    parts = api_duration.split(":")
                    duration_sec = int(parts[0]) * 60 + int(parts[1])

                view_count = v.get("play", 0)
                description = v.get("description", "")[:300]
                thumbnail = v.get("pic", "")
                if thumbnail:
                    if thumbnail.startswith("//"):
                        thumbnail = "https:" + thumbnail
                    elif thumbnail.startswith("http://"):
                        thumbnail = thumbnail.replace("http://", "https://", 1)

                # Use B站 API data directly — skip yt-dlp probes (too slow, adds marginal value)
                title_lower = title.lower()
                is_tutorial = any(kw in title_lower for kw in _TUTORIAL_KW)
                has_subtitles = False

                # Exclude game-related content entirely
                title_lower_full = title.lower()
                desc_lower = description.lower()
                if _is_domain_with_content_gate():
                    is_game = any(
                        kw.lower() in title_lower_full or kw.lower() in desc_lower
                        for kw in _get_game_exclude()
                    )
                    if is_game:
                        continue

                # Exclude advertising / scam / commercial content
                is_ad = any(
                    kw in title_lower_full or kw in desc_lower
                    for kw in _AD_EXCLUDE_KW
                )
                if is_ad:
                    continue

                # Content gate: skip non-tech junk (ads, games, food) — but only for domains with content gate
                is_junk = any(
                    kw in title_lower_full or kw in desc_lower
                    for kw in _get_non_tech_exclude()
                )
                if is_junk:
                    continue
                if _is_domain_with_content_gate():
                    has_tech_kw = any(
                        kw.lower() in title_lower_full or kw.lower() in desc_lower
                        for kw in _get_domain_required_kw()
                    )
                    if not has_tech_kw:
                        continue  # Not tech-related — skip for AI domain

                # Subtitled and tutorial videos are usable (user accepts subtitles)
                skip_reason = ""
                if is_tutorial:
                    skip_reason = "tutorial"
                elif has_subtitles:
                    skip_reason = "subtitles"

                results.append({
                    "title": title,
                    "url": url,
                    "duration_sec": duration_sec,
                    "platform": "bilibili",
                    "description": description,
                    "thumbnail": thumbnail,
                    "view_count": int(view_count) if view_count else 0,
                    "has_subtitles": has_subtitles,
                    "is_tutorial": is_tutorial,
                    "skip_reason": skip_reason,
                })

            logger.info("B站 search: %d results for '%s'", len(results), query)
            return results[:max_results]

        except Exception:
            logger.exception("B站 search failed for '%s'", query)
            return []

    # ---- Pexels ----------------------------------------------------------

    async def _search_pexels(
        self,
        query: str,
        max_results: int,
        min_dur: int,
        max_dur: int,
    ) -> list[dict[str, Any]]:
        """Search free stock footage via Pexels API (China-accessible).

        Pexels works best with English queries. Chinese queries are
        translated to English keywords for better results.
        """
        api_key = os.getenv("PEXELS_API_KEY", "")
        if not api_key:
            logger.warning("Pexels API key not configured — skipping")
            return []

        # Translate Chinese queries to English for Pexels compatibility
        pexels_query = _to_pexels_query(query)

        try:
            async with httpx.AsyncClient(timeout=30, proxy=_VIDEO_PROXY or None) as client:
                resp = await client.get(
                    self.PEXELS_BASE + "/search",
                    params={
                        "query": pexels_query,
                        "per_page": min(max_results, 15),
                        "orientation": "landscape",
                        "size": "medium",
                    },
                    headers={"Authorization": api_key},
                )
                if resp.status_code != 200:
                    logger.warning("Pexels API error %d: %s", resp.status_code, resp.text[:200])
                    return []

                data = resp.json()
                videos = data.get("videos", [])

                results: list[dict] = []
                for v in videos:
                    dur = v.get("duration", 30)
                    if dur < min_dur or dur > max_dur:
                        continue
                    # Content gate: skip non-tech/entertainment Pexels clips
                    title_from_url = v.get("url", "").split("/")[-2].replace("-", " ").lower()
                    if _is_domain_with_content_gate():
                        if any(kw in title_from_url for kw in _get_game_exclude()):
                            continue
                    if any(kw in title_from_url for kw in _get_non_tech_exclude()):
                        continue
                    # Pick best quality file under 1080p
                    files = sorted(
                        v.get("video_files", []),
                        key=lambda f: f.get("width", 0),
                        reverse=True,
                    )
                    best_file = files[0] if files else None
                    results.append({
                        "title": v.get("url", "").split("/")[-2].replace("-", " "),
                        "url": best_file.get("link", "") if best_file else "",
                        "duration_sec": dur,
                        "platform": "pexels",
                        "description": "",
                        "thumbnail": v.get("image", ""),
                        "width": best_file.get("width", 0) if best_file else 0,
                        "height": best_file.get("height", 0) if best_file else 0,
                    })

                logger.info("Pexels search: %d results for '%s'", len(results), query)
                return results[:max_results]

        except Exception:
            logger.exception("Pexels search failed for '%s'", query)
            return []

    # ---- YouTube ----------------------------------------------------------

    async def _search_youtube(
        self,
        query: str,
        max_results: int,
        min_dur: int,
        max_dur: int,
    ) -> list[dict[str, Any]]:
        """Search YouTube — API first (fast), yt-dlp as fallback (no quota).

        YouTube Data API v3 returns results in ~2-3s.  yt-dlp web scraping
        is slower (~15s) but has no quota limits.  We try API first, then
        fall back to yt-dlp only if the API key is missing or fails.
        """
        import json as _json
        import asyncio as _asyncio

        # Translate Chinese-heavy queries to English for better YouTube results
        search_query = _to_youtube_query(query)

        # ── Primary: YouTube Data API v3 (fast, 2-3s) ──
        api_key = os.getenv("YOUTUBE_API_KEY", "")
        if api_key:
            try:
                api_results = await asyncio.wait_for(
                    _asyncio.to_thread(self._search_youtube_api_sync,
                                       search_query, max_results, min_dur, max_dur),
                    timeout=8)
                if api_results:
                    logger.info("YouTube API search: %d results for '%s'", len(api_results), search_query[:50])
                    return api_results[:max_results]
            except Exception:
                pass  # Fall through to yt-dlp

        # ── Fallback: yt-dlp web scraping ──
        async def _try_ytdlp(q: str) -> list[dict]:
            """Run one yt-dlp search attempt."""
            try:
                cmd = [
                    "yt-dlp",
                    f"ytsearch{max_results}:{q}",
                    "--dump-json", "--skip-download",
                    "--no-playlist", "--socket-timeout", "15",
                ]
                if _VIDEO_PROXY:
                    cmd += ["--proxy", _VIDEO_PROXY]

                result = await self._run_subprocess(cmd, timeout=15)
                if result.returncode != 0:
                    stderr_tail = (result.stderr or "")[-200:]
                    logger.warning("yt-dlp YouTube search failed for '%s': %s", q, stderr_tail)
                    return []

                # Parse NDJSON output (one JSON object per line)
                results: list[dict] = []
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        meta = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue

                    title = meta.get("title", "") or ""
                    duration_sec = int(meta.get("duration", 0) or 0)
                    if duration_sec < min_dur or duration_sec > max_dur:
                        continue

                    vid = meta.get("id", "") or meta.get("display_id", "")
                    url = f"https://www.youtube.com/watch?v={vid}" if vid else meta.get("webpage_url", "")
                    if not url:
                        continue

                    description = (meta.get("description", "") or "")[:300]
                    view_count = int(meta.get("view_count", 0) or 0)

                    title_lower = title.lower()
                    desc_lower = description.lower()

                    # Game exclusion
                    if _is_domain_with_content_gate():
                        if any(kw.lower() in title_lower or kw.lower() in desc_lower
                               for kw in _get_game_exclude()):
                            continue

                    # Ad exclusion
                    if any(kw in title_lower or kw in desc_lower for kw in _AD_EXCLUDE_KW):
                        continue

                    # Non-tech exclusion (food, sports, entertainment, etc.)
                    if any(kw in title_lower or kw in desc_lower for kw in _get_non_tech_exclude()):
                        continue
                    # Tech keyword gate — only for AI/tech domain
                    if _is_domain_with_content_gate():
                        if not any(kw.lower() in title_lower or kw.lower() in desc_lower
                                  for kw in _get_domain_required_kw()):
                            continue

                    is_tutorial = any(kw in title_lower or kw in desc_lower for kw in _TUTORIAL_KW)

                    results.append({
                        "title": title,
                        "url": url,
                        "duration_sec": duration_sec,
                        "platform": "youtube",
                        "description": description,
                        "thumbnail": meta.get("thumbnail", ""),
                        "view_count": view_count,
                        "has_subtitles": True,
                        "is_tutorial": is_tutorial,
                        "skip_reason": "tutorial" if is_tutorial else "",
                    })
                return results
            except FileNotFoundError:
                logger.warning("yt-dlp not found")
                return []
            except Exception:
                logger.exception("yt-dlp YouTube search failed for '%s'", q)
                return []

        # ── Try query strategies (capped at 2 for speed — other sources run in parallel) ──
        _TUTORIAL_KW = ["教程", "课程", "合集", "教学", "讲解",
                       "入门", "速成", "零基础", "学习", "课堂",
                       "tutorial", "course", "guide", "how to", "beginner"]

        # Strategy 1: Translated English query (primary)
        results = await _try_ytdlp(search_query)
        logger.info("YouTube yt-dlp search #1: %d results for '%s' (EN='%s')",
                   len(results), query[:40], search_query)

        # Strategy 2: If 0 results, try with "AI" prefix for broader reach
        if not results and "AI" not in search_query and "artificial" not in search_query.lower():
            fallback_q = f"AI {search_query}"
            if fallback_q != search_query:
                results = await _try_ytdlp(fallback_q)
                logger.info("YouTube yt-dlp search #2: %d results for 'AI %s'", len(results), search_query[:40])

        if not results:
            # Final fallback to API (runs sync in executor — ok since only called when yt-dlp fails)
            api_results = self._search_youtube_api(search_query, max_results, min_dur, max_dur)
            if not api_results:
                api_results = self._search_youtube_api("AI technology news", max_results, min_dur, max_dur)
            return api_results

        return results[:max_results]

    def _search_youtube_api_sync(
        self, query: str, max_results: int, min_dur: int, max_dur: int,
    ) -> list[dict[str, Any]]:
        """YouTube Data API v3 search — synchronous, runs in thread pool."""
        api_key = os.getenv("YOUTUBE_API_KEY", "")
        if not api_key:
            return []
        import json as _json
        import isodate
        import urllib.request
        import urllib.parse

        try:
            # Search
            params = urllib.parse.urlencode({
                "part": "snippet", "q": query, "type": "video",
                "maxResults": min(max_results, 10), "key": api_key,
            })
            search_url = f"https://www.googleapis.com/youtube/v3/search?{params}"
            req = urllib.request.Request(search_url, headers={"User-Agent": "AiReport/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read())
            items = data.get("items", [])
            if not items:
                return []

            # Get video IDs
            video_ids = [it["id"]["videoId"] for it in items if "videoId" in it.get("id", {})]
            if not video_ids:
                return []

            # Details
            dparams = urllib.parse.urlencode({
                "part": "contentDetails,snippet,statistics",
                "id": ",".join(video_ids), "key": api_key,
            })
            durl = f"https://www.googleapis.com/youtube/v3/videos?{dparams}"
            dreq = urllib.request.Request(durl, headers={"User-Agent": "AiReport/1.0"})
            with urllib.request.urlopen(dreq, timeout=10) as resp:
                ddata = _json.loads(resp.read())
            detail_map = {v["id"]: v for v in ddata.get("items", [])}

            _TUTORIAL_KW = ["教程", "tutorial", "course", "guide", "how to"]
            results = []
            for item in items:
                vid = item["id"].get("videoId", "")
                if not vid:
                    continue
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")
                detail = detail_map.get(vid, {})
                dur_info = detail.get("contentDetails", {}).get("duration", "PT2M")
                try:
                    duration_sec = int(isodate.parse_duration(dur_info).total_seconds())
                except Exception:
                    duration_sec = 120
                if duration_sec < min_dur or duration_sec > max_dur:
                    continue
                title_lower = title.lower()
                if _is_domain_with_content_gate():
                    if any(kw.lower() in title_lower for kw in _get_game_exclude()):
                        continue
                if any(kw in title_lower for kw in _AD_EXCLUDE_KW):
                    continue
                if any(kw in title_lower for kw in _get_non_tech_exclude()):
                    continue
                stats = detail.get("statistics", {})
                results.append({
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "duration_sec": duration_sec,
                    "platform": "youtube",
                    "description": (snippet.get("description", "") or "")[:300],
                    "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                    "view_count": int(stats.get("viewCount", 0)),
                    "has_subtitles": True,
                    "is_tutorial": any(kw in title_lower for kw in _TUTORIAL_KW),
                    "skip_reason": "",
                })
            return results[:max_results]
        except Exception:
            return []

def _pexels_fallback_query() -> str:
    """Return a domain-aware fallback query for Pexels/YouTube English search.

    Uses the active domain config's pexels_query when available.
    Falls back to the old hardcoded default only when no domain is active.
    """
    if _active_domain_config is not None:
        dc = _active_domain_config
        pq = dc.get("pexels_query", "")
        if pq:
            # Strip Chinese chars — Pexels needs ASCII
            en = " ".join(w for w in pq.split() if all(ord(c) < 128 for c in w))
            if en.strip():
                return en
        # Build from broll_fallback
        fb = dc.get("broll_fallback", dc["display"])
        ascii_count = sum(1 for c in fb if ord(c) < 128)
        if ascii_count > len(fb) * 0.5:
            en = " ".join(w for w in fb.split() if all(ord(c) < 128 for c in w))
            if en.strip():
                return en
        # Translate common Chinese domain names to English
        _CN_TO_EN_DOMAIN = {
            "新能源": "renewable energy clean technology",
            "量子计算": "quantum computing technology",
            "区块链": "blockchain cryptocurrency",
            "游戏": "gaming esports video game",
            "教育": "education learning technology",
            "金融": "finance banking technology",
            "农业": "agriculture farming technology",
            "航天": "space aerospace technology",
            "人工智能": "artificial intelligence technology",
        }
        for cn, en in _CN_TO_EN_DOMAIN.items():
            if cn in dc["display"] or cn in dc["label"]:
                return en
        # Last resort: use display name with "technology"
        return f"{dc['display']} technology news"
    return "artificial intelligence technology"


def _to_youtube_query(query: str) -> str:
    """Convert any query to clean English for YouTube search.

    YouTube returns 0 results for Chinese/mixed queries via yt-dlp.
    This extracts English tokens and maps known Chinese keywords to
    produce a search that actually works on YouTube.
    """
    # ── Extract English tokens directly ──
    en_tokens = []
    for word in query.replace(",", " ").replace("，", " ").split():
        word = word.strip()
        if not word:
            continue
        # Keep pure ASCII words (3+ chars, not stopwords)
        if all(ord(c) < 128 for c in word):
            if len(word) >= 2 and word.lower() not in {
                "the", "and", "for", "its", "has", "new", "can", "not",
                "a", "an", "in", "of", "to", "is", "on", "at", "by",
            }:
                en_tokens.append(word)

    # ── Chinese → English keyword mapping ──
    keyword_map = [
        ("智能体", "AI agent"),
        ("大模型", "LLM large language model"),
        ("开源", "open source"),
        ("桌面", "desktop automation"),
        ("办公", "office AI agent"),
        ("编程", "coding AI programming"),
        ("机器人", "robot robotics"),
        ("自动驾驶", "self driving autonomous"),
        ("芯片", "chip semiconductor"),
        ("融资", "funding investment"),
        ("论文", "paper research"),
        ("发布", "release launch"),
        ("AI芯片", "AI chip processor"),
        ("算力", "computing power GPU"),
        ("腾讯", "Tencent"),
        ("百度", "Baidu"),
        ("阿里", "Alibaba"),
        ("华为", "Huawei"),
        ("字节", "ByteDance"),
        ("小米", "Xiaomi"),
        ("苹果", "Apple"),
        ("谷歌", "Google"),
        ("微软", "Microsoft"),
        ("Meta", "Meta"),
        ("NVIDIA", "NVIDIA"),
        ("OpenAI", "OpenAI"),
        ("DeepSeek", "DeepSeek"),
        ("Anthropic", "Anthropic"),
        ("Claude", "Claude"),
        ("GitHub", "GitHub"),
        ("特斯拉", "Tesla"),
        ("英伟达", "NVIDIA"),
        ("软银", "SoftBank"),
        ("三星", "Samsung"),
        # ── New additions ──
        ("工业", "industrial"),
        ("交付", "delivery deployment"),
        ("工厂", "factory manufacturing"),
        ("焊接", "welding"),
        ("具身智能", "embodied AI robotics"),
        ("安全", "security safety"),
        ("后门", "backdoor vulnerability"),
        ("漏洞", "vulnerability exploit"),
        ("能源", "energy power"),
        ("供应链", "supply chain"),
        ("物流", "logistics"),
        ("医疗", "medical healthcare"),
        ("金融", "finance fintech"),
        ("教育", "education learning"),
        ("游戏", "gaming"),
        ("视频", "video generation"),
        ("图像", "image generation"),
        ("语音", "voice speech"),
        ("数据库", "database"),
        ("云计算", "cloud computing"),
        ("边缘", "edge computing"),
        ("量子", "quantum computing"),
        ("至简动力", "robot delivery"),
        ("昇视唯盛", "welding robot"),
        ("深度智控", "energy AI"),
        ("工信部", "cybersecurity regulation"),
        # ── Sports / Esports ──
        ("体育", "sports"),
        ("电竞", "esports"),
        ("比赛", "match competition"),
        ("赛季", "season"),
        ("冠军", "champion"),
        ("联赛", "league"),
        ("球队", "team"),
        ("球员", "player"),
        ("转会", "transfer"),
        ("决赛", "final"),
        ("半决赛", "semifinal"),
        ("进球", "goal"),
        ("夺冠", "championship"),
        ("守望先锋", "Overwatch esports"),
        ("无畏契约", "Valorant esports"),
        ("英雄联盟", "League of Legends"),
        ("刀塔", "Dota"),
        ("国际邀请赛", "The International"),
        ("五杀", "pentakill"),
        ("季后赛", "playoffs"),
        ("选手", "player"),
        ("战队", "team"),
        ("纪录", "record"),
        ("新星", "rising star"),
        ("回归", "comeback return"),
        ("灵活战斗通行证", "battle pass gaming"),
        ("足球", "football soccer"),
        ("篮球", "basketball"),
        ("网球", "tennis"),
        ("F1", "Formula 1 racing"),
        ("UFC", "UFC fighting"),
        ("NBA", "NBA basketball"),
        ("英超", "Premier League"),
        ("西甲", "La Liga"),
        ("欧冠", "Champions League"),
        ("奥运会", "Olympics"),
        ("世界杯", "World Cup"),
        ("马拉松", "marathon"),
        ("游泳", "swimming"),
        ("田径", "athletics track field"),
        ("滑雪", "skiing snowboard"),
        ("体操", "gymnastics"),
        ("拳击", "boxing"),
        ("赛车", "racing motorsport"),
        ("自行车", "cycling"),
    ]
    for cn, en in keyword_map:
        if cn.lower() in query.lower():
            for en_word in en.split():
                if en_word.lower() not in [t.lower() for t in en_tokens]:
                    en_tokens.append(en_word)

    if en_tokens:
        # Deduplicate keeping order
        seen = set()
        unique = []
        for t in en_tokens:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique.append(t)
        return " ".join(unique[:6])
    # Domain-aware fallback: use the active domain's pexels_query or broll_fallback
    if _active_domain_config is not None:
        dc = _active_domain_config
        fb = dc.get("pexels_query", "") or dc.get("broll_fallback", "") or dc["display"]
        # Pexels query is already English; broll_fallback may be Chinese
        fb_en = _to_pexels_query(fb) if any(ord(c) >= 128 for c in fb) else fb
        return fb_en if fb_en else f"{dc['display']} news"

    return "AI technology news"


def _to_pexels_query(query: str) -> str:
    """Convert a Chinese search query to English keywords for Pexels API.

    Pexels returns poor results for Chinese queries. This maps common
    AI/tech Chinese terms to English equivalents and strips untranslated chars.
    """
    # If query is already mostly ASCII, extract only ASCII words
    ascii_count = sum(1 for c in query if ord(c) < 128)
    if ascii_count > len(query) * 0.5:
        ascii_words = " ".join(w for w in query.split() if all(ord(c) < 128 for c in w))
        if len(ascii_words.split()) >= 2:
            return ascii_words

    # Map of Chinese keywords → English Pexels-friendly terms
    keyword_map = [
        ("自动驾驶", "autonomous driving"),
        ("特斯拉", "tesla electric car"),
        ("编程", "coding programming"),
        ("代码", "programming code"),
        ("Copilot", "coding"),
        ("芯片", "computer chip"),
        ("机器人", "robot"),
        ("大模型", "AI artificial intelligence"),
        ("人工智能", "artificial intelligence"),
        ("AI", "artificial intelligence"),
        ("科技", "technology"),
        ("成本", "business finance"),
        ("支出", "business"),
        ("企业", "corporate business"),
        ("FSD", "self driving car"),
        ("初创", "startup business"),
        ("工厂", "factory automation"),
        ("数据", "data center server"),
        ("医疗", "medical technology"),
        ("金融", "finance banking"),
        ("教育", "education learning"),
        ("游戏", "gaming"),
        ("智能体", "AI agent software"),
        ("自动化", "automation software robot"),
        ("桌面", "computer desktop software"),
        ("办公", "office computer business"),
        ("操控", "computer control automation"),
        ("开源", "open source software code"),
        ("agent", "AI agent robotics"),
        ("多智能体", "multi agent AI collaboration"),
        ("编程智能体", "coding AI agent software"),
        ("办公智能体", "office AI automation agent"),
        ("桌面智能体", "desktop AI agent computer"),
        ("浏览器智能体", "browser automation AI"),
        ("工具调用", "software API integration"),
        ("工作流", "workflow automation process"),
        ("自主执行", "autonomous AI task execution"),
        ("GUI自动化", "GUI automation software"),
        ("本地智能体", "local AI software agent"),
        ("Agent框架", "AI agent framework software"),
        ("智能体协作", "AI agents collaboration team"),
        ("英伟达", "NVIDIA GPU technology"),
        ("NVIDIA", "NVIDIA graphics processor"),
        ("GPU", "graphics processor chip"),
        ("服务器", "data center server"),
        ("数据中心", "data center cloud computing"),
        ("人形机器人", "humanoid robot futuristic"),
        ("无人机", "drone aerial technology"),
        ("卫星", "satellite space technology"),
        ("新能源", "renewable energy clean technology"),
        ("手机", "smartphone mobile technology"),
        ("汽车", "automotive car technology"),
        ("网络安全", "cybersecurity network protection"),
        ("量子", "quantum computing technology"),
        ("VR", "virtual reality headset"),
        ("AR", "augmented reality glasses"),
        ("元宇宙", "digital virtual world metaverse"),
        ("脑机", "brain computer interface neural"),
        ("3D打印", "3D printing manufacturing"),
        # ── Company/entity names ──
        ("至简动力", "robot automation"),
        ("昇视唯盛", "welding robot industrial"),
        ("深度智控", "energy management AI"),
        ("工信部", "cybersecurity technology"),
        ("魔法原子", "AI robot"),
        ("宇树科技", "robot technology"),
        ("智元机器人", "humanoid robot"),
        ("百度", "Baidu technology"),
        ("腾讯", "Tencent technology"),
        ("阿里", "Alibaba cloud"),
        ("华为", "Huawei technology"),
        ("小米", "Xiaomi smartphone"),
        ("字节", "ByteDance technology"),
        ("美团", "Meituan delivery"),
        ("京东", "JD ecommerce"),
        ("蔚来", "NIO electric car"),
        ("小鹏", "XPeng electric car"),
        ("理想", "Li Auto electric car"),
        ("比亚迪", "BYD electric car"),
        ("工业", "industrial factory"),
        ("交付", "delivery deployment"),
        ("焊接", "welding manufacturing"),
        ("安全", "cybersecurity safety"),
        ("后门", "security vulnerability"),
        ("漏洞", "security exploit"),
        ("能源", "energy power"),
        ("融资", "investment funding business"),
        ("具身智能", "embodied AI robotics"),
        # ── More Chinese AI company names ──
        ("此芯科技", "chip semiconductor AI processor"),
        ("腾讯云ADP", "Tencent cloud AI agent platform"),
        ("腾讯云", "Tencent cloud computing"),
        ("面壁智能", "AI language model agent"),
        ("红熊AI", "AI memory technology startup"),
        ("红熊", "AI startup investment"),
        ("深鉴科技", "AI chip deep learning processor"),
        ("寒武纪", "Cambricon AI chip semiconductor"),
        ("壁仞科技", "GPU AI chip processor"),
        ("摩尔线程", "GPU computing AI chip"),
        ("燧原科技", "AI chip cloud computing"),
        ("地平线", "Horizon autonomous driving chip"),
        ("黑芝麻智能", "autonomous driving AI chip"),
        ("云从科技", "computer vision facial recognition"),
        ("智源研究院", "AI research institute Beijing"),
        ("智源", "AI research institute"),
        ("智谱", "AI large language model"),
        ("月之暗面", "Moonshot AI LLM"),
        ("百川智能", "Baichuan AI LLM model"),
        ("零一万物", "AI large model startup"),
        ("昆仑万维", "AI internet technology"),
        ("商汤", "SenseTime AI computer vision"),
        ("旷视", "Megvii computer vision AI"),
        ("SoulX", "AI agent startup"),
        ("高瓴创投", "venture capital investment"),
        ("波士顿动力", "Boston Dynamics robot"),
        ("世航智能", "drone maritime autonomous"),
        ("深度求索", "DeepSeek AI model"),
        ("MiniMax", "MiniMax AI model"),
        ("Figure AI", "humanoid robot"),
        ("Figure", "humanoid robot automation"),
        ("Claude", "Claude AI assistant"),
        ("Gemini", "Google Gemini AI model"),
        ("字节跳动", "ByteDance technology"),
        ("英伟达", "NVIDIA GPU technology"),
        ("NVIDIA", "NVIDIA graphics processor"),
        ("Anthropic", "Anthropic Claude AI"),
        ("DeepSeek", "DeepSeek AI LLM"),
        ("OpenAI", "OpenAI artificial intelligence"),
        ("GitHub", "GitHub open source code"),
        ("HuggingFace", "AI platform community"),
        ("特斯拉", "Tesla electric car"),
        ("Meta", "Meta AI technology"),
        ("三星", "Samsung electronics"),
        ("软银", "SoftBank investment"),
        ("ChatGPT", "ChatGPT conversational AI"),
        ("GPT", "large language model AI"),
        # ── Sports / Esports ──
        ("体育", "sports competition"),
        ("电竞", "esports gaming competition"),
        ("比赛", "sports match competition"),
        ("赛季", "sports season game"),
        ("冠军", "champion trophy"),
        ("联赛", "sports league"),
        ("球队", "sports team"),
        ("球员", "athlete player"),
        ("转会", "player transfer"),
        ("决赛", "final championship"),
        ("半决赛", "semifinal match"),
        ("进球", "goal score"),
        ("夺冠", "championship win"),
        ("守望先锋", "Overwatch esports gaming"),
        ("无畏契约", "Valorant esports gaming"),
        ("英雄联盟", "League of Legends gaming"),
        ("刀塔", "Dota gaming esports"),
        ("国际邀请赛", "esports tournament championship"),
        ("五杀", "pentakill gaming"),
        ("季后赛", "playoffs competition"),
        ("选手", "athlete player competition"),
        ("战队", "esports team"),
        ("纪录", "world record"),
        ("新星", "rising star rookie"),
        ("回归", "comeback return"),
        ("灵活战斗通行证", "battle pass gaming season"),
        ("足球", "football soccer"),
        ("篮球", "basketball"),
        ("网球", "tennis match"),
        ("F1", "Formula 1 racing"),
        ("UFC", "UFC fighting"),
        ("NBA", "NBA basketball"),
        ("英超", "Premier League football"),
        ("西甲", "La Liga football"),
        ("欧冠", "Champions League football"),
        ("奥运会", "Olympics sports"),
        ("世界杯", "World Cup football"),
        ("马拉松", "marathon running"),
        ("游泳", "swimming competition"),
        ("田径", "track field athletics"),
        ("滑雪", "skiing winter sports"),
        ("体操", "gymnastics competition"),
        ("拳击", "boxing fight"),
        ("赛车", "racing motorsport car"),
        ("自行车", "cycling race"),
    ]

    # Score each mapping and pick the best matches
    scores = []
    for cn, en in keyword_map:
        if cn.lower() in query.lower():
            scores.append((len(cn), en))
    scores.sort(reverse=True)

    if scores:
        result = " ".join(s[1] for s in scores[:3])
    else:
        result = _pexels_fallback_query()

    # Strip any remaining Chinese/non-ASCII chars that leaked through
    result = " ".join(w for w in result.split() if all(ord(c) < 128 for c in w))
    if not result.strip():
        result = _pexels_fallback_query()
    return result
