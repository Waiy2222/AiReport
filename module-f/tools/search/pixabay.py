"""Pixabay free media search — videos and photos.

Pixabay API: https://pixabay.com/api/docs/
- Free tier: ~100 req/min, no daily limit
- China-accessible without proxy
- Supports both videos (/api/videos/) and photos (/api/)
- Chinese queries work (auto-translated by Pixabay)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
PIXABAY_PHOTO_URL = "https://pixabay.com/api/"


class PixabaySearcher:
    """Search Pixabay for free videos and photos.

    Usage::

        searcher = PixabaySearcher()
        videos = await searcher.search_videos("AI robot", max_results=10)
        photos = await searcher.search_photos("technology", max_results=5)
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("PIXABAY_API_KEY", "")
        if not self.api_key:
            logger.warning("PIXABAY_API_KEY not set — Pixabay search disabled")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    # ── Video search ───────────────────────────────────────────────

    async def search_videos(
        self,
        query: str,
        max_results: int = 10,
        min_duration: int = 5,
        max_duration: int = 300,
        min_width: int = 640,
    ) -> list[dict[str, Any]]:
        """Search Pixabay for free stock videos.

        Returns list of dicts compatible with VideoSearcher result format.
        """
        if not self.available:
            return []

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    PIXABAY_VIDEO_URL,
                    params={
                        "key": self.api_key,
                        "q": query[:100],
                        "per_page": min(max_results, 20),
                        "lang": "zh",  # Chinese + English support
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Pixabay video API %d: %s", resp.status_code, resp.text[:200])
                    return []

                data = resp.json()
                hits = data.get("hits", [])

                results: list[dict] = []
                for v in hits:
                    dur = v.get("duration", 30)
                    if dur < min_duration or dur > max_duration:
                        continue

                    # Pick best quality video file
                    videos = v.get("videos", {})
                    # Quality order: large → medium → small
                    for quality in ("large", "medium", "small"):
                        vf = videos.get(quality, {})
                        if not vf:
                            continue
                        w = vf.get("width", 0)
                        if w >= min_width:
                            results.append({
                                "title": v.get("tags", ""),
                                "url": vf.get("url", ""),
                                "duration_sec": dur,
                                "platform": "pixabay",
                                "description": "",
                                "thumbnail": v.get("userImageURL", ""),
                                "width": w,
                                "height": vf.get("height", 0),
                                "type": "video",
                                "pixabay_id": v.get("id"),
                                "page_url": v.get("pageURL", ""),
                            })
                            break  # got the best quality, stop

                logger.info("Pixabay video: %d results for '%s'", len(results), query[:50])
                return results[:max_results]

        except Exception:
            logger.exception("Pixabay video search failed for '%s'", query)
            return []

    # ── Photo search ───────────────────────────────────────────────

    async def search_photos(
        self,
        query: str,
        max_results: int = 10,
        min_width: int = 800,
        orientation: str = "horizontal",
    ) -> list[dict[str, Any]]:
        """Search Pixabay for free stock photos.

        Returns list of dicts compatible with VideoSearcher image result format.
        """
        if not self.available:
            return []

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    PIXABAY_PHOTO_URL,
                    params={
                        "key": self.api_key,
                        "q": query[:100],
                        "per_page": min(max_results, 20),
                        "lang": "zh",
                        "orientation": orientation,
                        "min_width": min_width,
                        "safesearch": "true",
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Pixabay photo API %d: %s", resp.status_code, resp.text[:200])
                    return []

                data = resp.json()
                hits = data.get("hits", [])

                results: list[dict] = []
                for p in hits:
                    image_url = p.get("largeImageURL") or p.get("webformatURL", "")
                    if not image_url:
                        continue

                    results.append({
                        "title": p.get("tags", ""),
                        "url": image_url,
                        "duration_sec": 5,  # default for Ken Burns
                        "platform": "pixabay_photo",
                        "description": f"Photo by {p.get('user', '')}",
                        "thumbnail": p.get("previewURL", ""),
                        "width": p.get("imageWidth", 0),
                        "height": p.get("imageHeight", 0),
                        "type": "image",
                        "pixabay_id": p.get("id"),
                        "page_url": p.get("pageURL", ""),
                    })

                logger.info("Pixabay photo: %d results for '%s'", len(results), query[:50])
                return results[:max_results]

        except Exception:
            logger.exception("Pixabay photo search failed for '%s'", query)
            return []

    # ── Combined search ────────────────────────────────────────────

    async def search(
        self,
        query: str,
        max_videos: int = 6,
        max_photos: int = 4,
    ) -> dict[str, list[dict]]:
        """Search both videos and photos concurrently."""
        videos, photos = await asyncio.gather(
            self.search_videos(query, max_results=max_videos),
            self.search_photos(query, max_results=max_photos),
        )
        return {"videos": videos, "photos": photos}
