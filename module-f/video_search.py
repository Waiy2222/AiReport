"""Video clip search and download.

Searches Bilibili (primary), Pexels (free stock footage), and optionally
YouTube for AI/agent-related video clips.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path(os.getenv("VIDEO_DOWNLOAD_DIR", "./downloads")).resolve()
SEARCH_SOURCES = os.getenv("VIDEO_SEARCH_SOURCES", "bilibili").split(",")
BILIBILI_MAX_DURATION = int(os.getenv("BILIBILI_MAX_DURATION", "600"))  # seconds
BILIBILI_MAX_RESULTS = int(os.getenv("BILIBILI_MAX_RESULTS", "10"))

# Game-related keywords to EXCLUDE from B-roll results entirely
_GAME_EXCLUDE_KW = [
    "游戏", "电竞", "王者荣耀", "英雄联盟", "原神", "崩坏", "星穹铁道",
    "明日方舟", "我的世界", "吃鸡", "绝地求生", "赛博朋克", "魔兽世界",
    "魔兽", "梦幻西游", "地下城", "和平精英", "蛋仔派对", "第五人格",
    "阴阳师", "光遇", "永劫无间", "守望先锋", "炉石传说", "怪物猎人",
    "最终幻想", "剑网", "逆水寒", "天龙八部", "征途", "迷你世界",
    "暗黑破坏神", "使命召唤", "穿越火线", "CF", "生死狙击", "全民枪战",
    "部落冲突", "皇室战争", "荒野乱斗", "宝可梦", "精灵宝可梦",
    "Minecraft", "LOL", "PUBG", "DNF", "WOW", "Genshin", "Honkai",
]

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

    def __init__(self):
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    async def search(
        self,
        query: str,
        max_results: int = 10,
        min_duration_sec: int = 10,
        max_duration_sec: int = 300,
    ) -> list[dict[str, Any]]:
        """Search for video clips matching a query.

        B站 first (more news-relevant), Pexels as fallback (generic stock).
        Tutorial/subtitled B站 videos included but lowest priority.
        """
        pexels_results: list[dict] = []
        bili_clean: list[dict] = []
        bili_tutorial: list[dict] = []

        for source in SEARCH_SOURCES:
            source = source.strip()
            if source == "pexels":
                pexels_results = await self._search_pexels(
                    query, max_results, min_duration_sec, max_duration_sec
                )
            elif source == "bilibili":
                r = await self._search_bilibili(query, max_results)
                for v in r:
                    if v.get("is_tutorial"):
                        bili_tutorial.append(v)  # tutorials lowest priority
                    else:
                        bili_clean.append(v)  # clean + subtitled both OK

        # Priority: B站 (clean+subtitled) → B站 tutorials → Pexels
        results = bili_clean + bili_tutorial + pexels_results

        logger.info("Video search for '%s': %d results (B站:%d Pexels:%d)",
                    query, len(results),
                    len(bili_clean) + len(bili_tutorial),
                    len(pexels_results))
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
        # B站 / YouTube — use yt-dlp
        if "bilibili.com" in video_url or "youtube.com" in video_url or "youtu.be" in video_url:
            return await self._download_ytdlp(video_url, start_sec, end_sec)

        # Pexels / direct URLs — httpx download with retry
        import asyncio as _asyncio
        last_error = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=120, proxy=None) as client:
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
            "--proxy", "",
            "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "-o", out_template,
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--socket-timeout", "30",
            "--retries", "5",
            "--fragment-retries", "5",
            "--extractor-retries", "5",
        ]

        # Download a segment if specified
        if end_sec is not None and end_sec > start_sec:
            cmd_base += ["--download-sections", f"*{start_sec}-{end_sec}"]

        last_error = None
        for attempt in range(5):
            cmd = cmd_base + [video_url]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                        encoding="utf-8", errors="replace")
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

        logger.warning("yt-dlp download failed after 5 attempts: %s", video_url)
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
            async with httpx.AsyncClient(timeout=30, proxy=None) as client:
                resp = await client.get(search_url, headers=headers)
                # Retry up to 3 times with backoff for 412 rate limiting
                retry = 0
                while resp.status_code == 412 and retry < 3:
                    wait = 2 * (retry + 1)  # 2s, 4s, 6s
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
                thumbnail = v.get("pic", "").replace("http://", "https://", 1) if v.get("pic") else ""

                # Check title for tutorial keywords
                title_lower = title.lower()
                is_tutorial = any(kw in title_lower for kw in _TUTORIAL_KW)
                has_subtitles = False

                # Try yt-dlp for metadata and subtitle detection
                try:
                    cmd2 = [
                        "yt-dlp",
                        "--proxy", "",
                        "--dump-json",
                        "--skip-download",
                        "--no-playlist",
                        "--socket-timeout", "20",
                        url,
                    ]
                    r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=30,
                                        encoding="utf-8", errors="replace")
                    if r2.returncode == 0 and r2.stdout.strip():
                        meta = _json.loads(r2.stdout.strip().split("\n")[-1])
                        yt_duration = meta.get("duration")
                        if yt_duration:
                            duration_sec = int(yt_duration)
                        yt_title = meta.get("title")
                        if yt_title:
                            title = yt_title

                        # Detect subtitle tracks
                        subs = meta.get("subtitles", {})
                        auto_subs = meta.get("automatic_captions", {})
                        if subs or auto_subs:
                            # Check for Chinese subtitle tracks
                            all_sub_langs = set(subs.keys()) | set(auto_subs.keys())
                            if any(lang.startswith("zh") for lang in all_sub_langs):
                                has_subtitles = True
                        # Also check description for subtitle indicators
                        yt_desc = (meta.get("description", "") or "").lower()
                        if any(kw in yt_desc for kw in ["字幕", "cc", "subtitles"]):
                            has_subtitles = True
                except Exception:
                    pass  # Use API values as fallback

                # Exclude game-related content entirely
                title_lower_full = title.lower()
                desc_lower = description.lower()
                is_game = any(
                    kw.lower() in title_lower_full or kw.lower() in desc_lower
                    for kw in _GAME_EXCLUDE_KW
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
            async with httpx.AsyncClient(timeout=30, proxy=None) as client:
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
                        "description": f"Pexels: {query}",
                        "thumbnail": v.get("image", ""),
                        "width": best_file.get("width", 0) if best_file else 0,
                        "height": best_file.get("height", 0) if best_file else 0,
                    })

                logger.info("Pexels search: %d results for '%s'", len(results), query)
                return results[:max_results]

        except Exception:
            logger.exception("Pexels search failed for '%s'", query)
            return []

    # ---- YouTube (requires VPN from China) -------------------------------

    async def _search_youtube(
        self,
        query: str,
        max_results: int,
        min_dur: int,
        max_dur: int,
    ) -> list[dict[str, Any]]:
        """Search YouTube via Data API v3 (requires YOUTUBE_API_KEY)."""
        api_key = os.getenv("YOUTUBE_API_KEY", "")
        if not api_key:
            logger.info("YouTube API key not configured — skip")
            return []

        # TODO: YouTube Data API v3 call
        # url = "https://www.googleapis.com/youtube/v3/search"
        raise NotImplementedError(
            "YouTube search pending — set YOUTUBE_API_KEY and implement API call"
        )



# ---- Pexels query translation -----------------------------------------------

def _to_pexels_query(query: str) -> str:
    """Convert a Chinese search query to English keywords for Pexels API.

    Pexels returns poor results for Chinese queries. This maps common
    AI/tech Chinese terms to English equivalents.
    """
    # If query is already mostly ASCII, use it as-is
    ascii_count = sum(1 for c in query if ord(c) < 128)
    if ascii_count > len(query) * 0.5:
        return query

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
    ]

    # Score each mapping and pick the best 1-2
    scores = []
    for cn, en in keyword_map:
        if cn.lower() in query.lower():
            # Score by match length (longer match = more specific)
            scores.append((len(cn), en))
    scores.sort(reverse=True)

    if scores:
        # Use top 2 matches
        return " ".join(s[1] for s in scores[:2])

    # Generic fallback for Chinese queries
    return "artificial intelligence technology"
