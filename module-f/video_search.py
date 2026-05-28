"""Video clip search and download.

Phase 2: implemented YouTube Data API v3 search + yt-dlp download.
Graceful mock fallback when APIs are unavailable.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
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
                query, max_results, min_duration_sec, max_duration_sec,
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
        """Download a video clip (or segment) and return local file path.

        Uses yt-dlp when available; falls back to mock for testing.
        """
        output_template = str(DOWNLOAD_DIR / "%(id)s_%(title)s.%(ext)s")

        try:
            cmd = [
                "yt-dlp",
                "-f", "best[height<=720]",
                "--output", output_template,
                "--no-playlist",
                "--print", "filename",
            ]
            if end_sec is not None:
                cmd.extend(["--download-sections", f"*{start_sec}-{end_sec}"])
            elif start_sec > 0:
                cmd.extend(["--download-sections", f"*{start_sec}-inf"])
            cmd.append(video_url)

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                logger.warning("yt-dlp download failed: %s", result.stderr[:300])
                return None

            output_path = result.stdout.strip().split("\n")[-1]
            if output_path and Path(output_path).exists():
                logger.info("Downloaded: %s", output_path)
                return output_path

            logger.warning("yt-dlp reported success but file not found")
            return None

        except FileNotFoundError:
            logger.warning(
                "yt-dlp not installed. Install with: pip install yt-dlp"
            )
            return self._mock_download(video_url, start_sec, end_sec)
        except subprocess.TimeoutExpired:
            logger.warning("yt-dlp download timed out for %s", video_url)
            return None
        except Exception as e:
            logger.warning("yt-dlp download failed: %s", e)
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

    # ---- internal -----------------------------------------------------

    async def _search_youtube(
        self,
        query: str,
        max_results: int,
        min_dur: int,
        max_dur: int,
    ) -> list[dict[str, Any]]:
        """Search YouTube via Data API v3. Falls back to mock on failure."""
        api_key = os.getenv("YOUTUBE_API_KEY", "")
        if not api_key:
            logger.warning("YouTube API key not configured — using mock")
            return self._mock_results(query, max_results)

        try:
            import httpx

            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": min(max_results, 50),
                "key": api_key,
                "videoDuration": "any",
                "fields": "items(id(videoId),snippet(title,description,channelTitle,thumbnails(default(url))))",
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            results: list[dict] = []
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId", "")

                # Get video duration via videos endpoint
                dur = await self._get_youtube_duration(api_key, video_id)
                if dur is not None and not (min_dur <= dur <= max_dur):
                    continue

                results.append({
                    "title": snippet.get("title", ""),
                    "url": f"https://youtube.com/watch?v={video_id}",
                    "duration_sec": dur or 60,
                    "platform": "youtube",
                    "description": snippet.get("description", "")[:300],
                    "thumbnail": (
                        snippet.get("thumbnails", {})
                        .get("default", {})
                        .get("url", "")
                    ),
                })

            return results[:max_results]

        except Exception as e:
            logger.warning("YouTube API search failed: %s — using mock", e)
            return self._mock_results(query, max_results)

    async def _get_youtube_duration(
        self, api_key: str, video_id: str
    ) -> int | None:
        """Get video duration in seconds from YouTube Data API."""
        if not video_id:
            return None
        try:
            import httpx

            url = "https://www.googleapis.com/youtube/v3/videos"
            params = {
                "part": "contentDetails",
                "id": video_id,
                "key": api_key,
                "fields": "items(contentDetails(duration))",
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            for item in data.get("items", []):
                iso_dur = item.get("contentDetails", {}).get("duration", "PT0S")
                return self._parse_iso_duration(iso_dur)

        except Exception as e:
            logger.debug("Failed to get video duration: %s", e)
            return None

    @staticmethod
    def _parse_iso_duration(iso: str) -> int:
        """Parse ISO 8601 duration string (e.g. PT1M30S) to seconds."""
        import re
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    def _mock_download(
        self, url: str, start_sec: float, end_sec: float | None
    ) -> str | None:
        """Create a minimal mock video file for testing."""
        import uuid
        mock_path = str(DOWNLOAD_DIR / f"mock_{uuid.uuid4().hex[:8]}.mp4")
        # Write minimal mp4 placeholder
        try:
            with open(mock_path, "wb") as f:
                f.write(b"\x00\x00\x00\x1cftypmp42")
            logger.warning("Created mock download: %s", mock_path)
            return mock_path
        except OSError as e:
            logger.warning("Mock download failed: %s", e)
            return None

    def _mock_results(self, query: str, count: int) -> list[dict]:
        return [
            {
                "title": f"[mock] {query} - result {i+1}",
                "url": f"https://youtube.com/watch?v=mock{i+1}",
                "duration_sec": 60 + i * 30,
                "platform": "youtube",
                "description": f"Mock search result for {query}",
                "thumbnail": "",
            }
            for i in range(min(count, 5))
        ]
