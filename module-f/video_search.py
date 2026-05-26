"""Video clip search and download.

Searches YouTube (and optionally other platforms) for AI/agent-related
video clips, downloads them for analysis and editing.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path(os.getenv("VIDEO_DOWNLOAD_DIR", "./downloads")).resolve()
SEARCH_SOURCES = os.getenv("VIDEO_SEARCH_SOURCES", "youtube").split(",")


class VideoSearcher:
    """Search and download video clips from the web."""

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

        if "youtube" in SEARCH_SOURCES:
            yt_results = await self._search_youtube(
                query, max_results, min_duration_sec, max_duration_sec
            )
            results.extend(yt_results)

        logger.info("Video search for '%s': %d results", query, len(results))
        return results

    async def download(
        self,
        video_url: str,
        start_sec: float = 0,
        end_sec: float | None = None,
    ) -> str | None:
        """Download a video clip (or segment) and return local file path."""
        # TODO: implement yt-dlp download
        # import subprocess
        # cmd = ["yt-dlp", "-f", "best[height<=720]", "--output", ...]
        raise NotImplementedError("Video download pending — install yt-dlp")

    async def search_by_preferences(
        self,
        user_tags: list[str],
        briefing_topics: list[str],
        max_results: int = 15,
    ) -> list[dict[str, Any]]:
        """Build search queries from user preferences and briefing topics."""
        all_queries = set(user_tags + briefing_topics)
        all_queries.discard("")  # remove empty

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

    # ---- internal -----------------------------------------------------

    async def _search_youtube(
        self,
        query: str,
        max_results: int,
        min_dur: int,
        max_dur: int,
    ) -> list[dict[str, Any]]:
        """Search YouTube via Data API v3."""
        api_key = os.getenv("YOUTUBE_API_KEY", "")
        if not api_key:
            logger.warning("YouTube API key not configured — skip YouTube search")
            return self._mock_results(query, max_results)

        # TODO: implement YouTube Data API v3 call
        # url = "https://www.googleapis.com/youtube/v3/search"
        # params = {"part":"snippet","q":query,"type":"video",...}
        raise NotImplementedError(
            "YouTube search pending — set YOUTUBE_API_KEY env var"
        )

    def _mock_results(self, query: str, count: int) -> list[dict]:
        return [
            {
                "title": f"[mock] {query} - result {i+1}",
                "url": f"https://youtube.com/watch?v=mock{i+1}",
                "duration_sec": 60 + i * 30,
                "platform": "youtube",
                "description": f"Mock result for {query}",
                "thumbnail": "",
            }
            for i in range(min(count, 3))
        ]
