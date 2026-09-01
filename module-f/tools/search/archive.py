"""Internet Archive search — free public domain footage and media.

Archive.org has millions of freely-licensed videos, films, newsreels:
- Historical technology footage (old computers, factories, labs)
- News broadcasts and documentaries
- Scientific films and educational content
- Public domain NASA footage

API: https://archive.org/advancedsearch.php (no key, no auth, no rate limit)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ARCHIVE_SEARCH = "https://archive.org/advancedsearch.php"


class ArchiveSearcher:
    """Search Internet Archive for public domain videos and media.

    Usage::

        searcher = ArchiveSearcher()
        videos = await searcher.search_videos("computer history", max_results=10)
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def search_videos(
        self,
        query: str,
        max_results: int = 10,
        min_duration: int = 0,
        max_duration: int = 600,
    ) -> list[dict[str, Any]]:
        """Search Archive.org for videos.

        Strategy: search for 'movies' mediatype, then fetch metadata
        for each result to get file URLs and durations.
        """
        client = await self._get_client()

        try:
            # Step 1: Search
            resp = await client.get(
                ARCHIVE_SEARCH,
                params={
                    "q": f"({query}) AND mediatype:(movies)",
                    "fl[]": ["identifier", "title", "description", "year", "date"],
                    "rows": min(max_results * 2, 30),
                    "output": "json",
                    "sort": ["downloads desc"],
                },
            )
            if resp.status_code != 200:
                logger.warning("Archive.org search HTTP %d", resp.status_code)
                return []

            data = resp.json()
            docs = data.get("response", {}).get("docs", [])
            if not docs:
                logger.info("Archive.org: 0 videos for '%s'", query[:50])
                return []

            # Step 2: Get file details for each item
            results: list[dict] = []
            for doc in docs[:max_results * 2]:
                identifier = doc.get("identifier", "")
                if not identifier:
                    continue

                try:
                    meta_url = f"https://archive.org/metadata/{identifier}"
                    meta_resp = await client.get(meta_url)
                    if meta_resp.status_code != 200:
                        continue

                    meta = meta_resp.json()
                    files = meta.get("files", [])
                    if not files:
                        continue

                    # Pick the best video file
                    video_file = None
                    for f in files:
                        fmt = f.get("format", "").lower()
                        if fmt in ("mp4", "h.264", "mpeg4", "h.264 ia", "movie"):
                            if video_file is None or f.get("size", 0) > video_file.get("size", 0):
                                video_file = f

                    if not video_file:
                        # Try any file with video extensions
                        for f in files:
                            name = f.get("name", "").lower()
                            if name.endswith((".mp4", ".webm", ".ogv", ".avi")):
                                if video_file is None or f.get("size", 0) > video_file.get("size", 0):
                                    video_file = f

                    if not video_file:
                        continue

                    # Get duration from metadata
                    duration = float(meta.get("metadata", {}).get("runtime", 0) or 0)
                    if not duration and video_file:
                        duration = float(video_file.get("length", 0) or 0)
                    if not duration:
                        duration = 60  # default assumption

                    if duration < min_duration or duration > max_duration:
                        continue

                    # Build download URL
                    file_name = video_file.get("name", "")
                    download_url = f"https://archive.org/download/{identifier}/{file_name}"

                    # Thumbnail
                    thumbnail = ""
                    for f in files:
                        if f.get("format", "") in ("Thumbnail", "JPEG Thumb"):
                            thumbnail = f"https://archive.org/download/{identifier}/{f.get('name', '')}"
                            break

                    title = doc.get("title", "") or identifier
                    desc = doc.get("description", "") or ""

                    results.append({
                        "title": title,
                        "url": download_url,
                        "duration_sec": min(duration, 600),
                        "platform": "archive",
                        "description": (desc or "")[:300],
                        "thumbnail": thumbnail,
                        "width": 640,
                        "height": 480,
                        "type": "video",
                        "year": doc.get("year", ""),
                        "identifier": identifier,
                    })

                    if len(results) >= max_results:
                        break

                except Exception:
                    continue  # skip problematic items

            logger.info("Archive.org: %d videos for '%s'", len(results), query[:50])
            return results[:max_results]

        except Exception:
            logger.exception("Archive.org search failed for '%s'", query)
            return []

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
