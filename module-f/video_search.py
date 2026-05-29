"""Video clip search and download.

Searches Pexels (free stock footage, China-accessible) and optionally
YouTube / Bilibili for AI/agent-related video clips.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path(os.getenv("VIDEO_DOWNLOAD_DIR", "./downloads")).resolve()
SEARCH_SOURCES = os.getenv("VIDEO_SEARCH_SOURCES", "pexels").split(",")


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

        Returns list of dicts with keys: title, url, duration_sec,
        thumbnail, platform, description.
        """
        results: list[dict] = []

        for source in SEARCH_SOURCES:
            source = source.strip()
            if source == "pexels":
                r = await self._search_pexels(
                    query, max_results, min_duration_sec, max_duration_sec
                )
                results.extend(r)
            elif source == "youtube":
                r = await self._search_youtube(
                    query, max_results, min_duration_sec, max_duration_sec
                )
                results.extend(r)

        logger.info("Video search for '%s': %d results", query, len(results))
        return results

    async def download(
        self,
        video_url: str,
        start_sec: float = 0,
        end_sec: float | None = None,
    ) -> str | None:
        """Download a video clip and return local file path."""
        # For Pexels, download the direct video file
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(video_url)
                if resp.status_code == 200:
                    filename = Path(video_url).name or f"clip_{hash(video_url)}.mp4"
                    out_path = str(DOWNLOAD_DIR / filename)
                    with open(out_path, "wb") as f:
                        f.write(resp.content)
                    logger.info("Downloaded: %s -> %s", video_url, out_path)
                    return out_path
        except Exception:
            logger.warning("Download failed for %s", video_url)

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

    # ---- Pexels ----------------------------------------------------------

    async def _search_pexels(
        self,
        query: str,
        max_results: int,
        min_dur: int,
        max_dur: int,
    ) -> list[dict[str, Any]]:
        """Search free stock footage via Pexels API (China-accessible)."""
        api_key = os.getenv("PEXELS_API_KEY", "")
        if not api_key:
            logger.warning("Pexels API key not configured — using mock")
            return self._mock_results(query, max_results // 2)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    self.PEXELS_BASE + "/search",
                    params={
                        "query": query,
                        "per_page": min(max_results, 15),
                        "orientation": "landscape",
                        "size": "medium",
                    },
                    headers={"Authorization": api_key},
                )
                if resp.status_code != 200:
                    logger.warning("Pexels API error %d: %s", resp.status_code, resp.text[:200])
                    return self._mock_results(query, max_results // 2)

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
            return self._mock_results(query, max_results // 2)

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

    # ---- mock ------------------------------------------------------------

    def _mock_results(self, query: str, count: int) -> list[dict]:
        return [
            {
                "title": f"[mock] {query} - result {i+1}",
                "url": f"https://example.com/video/mock{i+1}.mp4",
                "duration_sec": 60 + i * 30,
                "platform": "mock",
                "description": f"Mock result for {query}",
                "thumbnail": "",
                "width": 1920,
                "height": 1080,
            }
            for i in range(min(count, 3))
        ]
