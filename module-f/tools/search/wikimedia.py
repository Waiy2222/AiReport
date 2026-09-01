"""Wikimedia Commons search — completely free, no API key, no auth.

Wikimedia Commons has millions of freely-licensed media files:
- Company logos, product photos, tech diagrams
- Science/technology illustrations
- Historical footage
- All CC-licensed or public domain

API: https://commons.wikimedia.org/w/api.php
No rate limit for reasonable use.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote, urlencode

import httpx

logger = logging.getLogger(__name__)

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"


class WikimediaSearcher:
    """Search Wikimedia Commons for freely-licensed images and media.

    Usage::

        searcher = WikimediaSearcher()
        images = await searcher.search_images("NVIDIA GPU", max_results=10)
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30,
                headers={"User-Agent": "AiNewsBriefing/1.0 (tech-news-bot; contact@example.com)"},
            )
        return self._client

    async def search_images(
        self,
        query: str,
        max_results: int = 10,
        min_width: int = 400,
        min_height: int = 300,
    ) -> list[dict[str, Any]]:
        """Search Wikimedia Commons for images.

        Returns list of dicts with: title, url, thumbnail, width, height,
        description, license, platform='wikimedia', type='image'.
        """
        client = await self._get_client()

        try:
            # Step 1: Search for files (with rate-limit retry)
            search_params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": f"{query} filetype:bitmap|drawing",
                "srnamespace": "6",  # File namespace
                "srlimit": str(min(max_results * 2, 30)),
                "srprop": "snippet|titlesnippet",
            }

            resp = await client.get(WIKIMEDIA_API, params=search_params)
            # Retry on rate limit (429)
            if resp.status_code == 429:
                await asyncio.sleep(3)
                resp = await client.get(WIKIMEDIA_API, params=search_params)
            if resp.status_code != 200:
                logger.warning("Wikimedia search HTTP %d", resp.status_code)
                return []

            data = resp.json()
            pages = data.get("query", {}).get("search", [])
            if not pages:
                logger.info("Wikimedia: 0 results for '%s'", query[:50])
                return []

            # Step 2: Get image info for found files
            titles = "|".join(p["title"] for p in pages[:max_results * 2])
            image_params = {
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "titles": titles,
                "iiprop": "url|size|extmetadata|mime|thumbmime",
                "iiurlwidth": "800",  # Request thumbnail for preview
                "iilimit": "1",
            }

            resp2 = await client.get(WIKIMEDIA_API, params=image_params)
            if resp2.status_code != 200:
                logger.warning("Wikimedia imageinfo HTTP %d", resp2.status_code)
                return []

            data2 = resp2.json()
            pages_dict = data2.get("query", {}).get("pages", {})

            results: list[dict] = []
            for page_id, page_info in pages_dict.items():
                if page_id == "-1":
                    continue

                image_info = page_info.get("imageinfo", [])
                if not image_info:
                    continue

                info = image_info[0]
                mime = info.get("mime", "")

                # Skip non-image files (SVG, PDF, audio, video for now)
                if mime not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
                    continue

                width = info.get("width", 0)
                height = info.get("height", 0)
                if width < min_width or height < min_height:
                    continue

                url = info.get("url", "")
                thumb_url = info.get("thumburl", url)
                description_url = info.get("descriptionurl", "")

                # Extract metadata
                extmeta = info.get("extmetadata", {})
                license_info = extmeta.get("LicenseShortName", {}).get("value", "CC")
                artist = extmeta.get("Artist", {}).get("value", "")
                desc = extmeta.get("ImageDescription", {}).get("value", "")

                results.append({
                    "title": page_info.get("title", "").replace("File:", ""),
                    "url": url,
                    "thumbnail": thumb_url,
                    "width": width,
                    "height": height,
                    "description": desc or "",
                    "artist": artist,
                    "license": license_info,
                    "page_url": description_url,
                    "platform": "wikimedia",
                    "type": "image",
                    "duration_sec": 5,
                })

            # Sort by resolution (prefer larger images)
            results.sort(key=lambda x: x["width"] * x["height"], reverse=True)
            logger.info("Wikimedia: %d images for '%s'", len(results), query[:50])
            return results[:max_results]

        except Exception:
            logger.exception("Wikimedia search failed for '%s'", query)
            return []

    async def search_videos(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Search Wikimedia Commons for videos (WebM/OGG).

        Note: Wikimedia videos are typically lower quality and shorter,
        but 100% free and public domain. Good for background/atmospheric footage.
        """
        client = await self._get_client()

        try:
            search_params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": f"{query} filetype:video",
                "srnamespace": "6",
                "srlimit": str(min(max_results * 2, 20)),
            }

            resp = await client.get(WIKIMEDIA_API, params=search_params)
            # Retry on rate limit (429)
            if resp.status_code == 429:
                await asyncio.sleep(3)
                resp = await client.get(WIKIMEDIA_API, params=search_params)
            if resp.status_code != 200:
                return []

            data = resp.json()
            pages = data.get("query", {}).get("search", [])
            if not pages:
                return []

            titles = "|".join(p["title"] for p in pages[:max_results * 2])
            image_params = {
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "titles": titles,
                "iiprop": "url|size|mime|extmetadata",
                "iilimit": "1",
            }

            resp2 = await client.get(WIKIMEDIA_API, params=image_params)
            if resp2.status_code != 200:
                return []

            data2 = resp2.json()
            pages_dict = data2.get("query", {}).get("pages", {})

            results: list[dict] = []
            for page_id, page_info in pages_dict.items():
                if page_id == "-1":
                    continue

                info_list = page_info.get("imageinfo", [])
                if not info_list:
                    continue

                info = info_list[0]
                mime = info.get("mime", "")

                # Only video formats
                if mime not in ("video/webm", "video/ogg", "video/mp4"):
                    continue

                url = info.get("url", "")
                if not url:
                    continue

                results.append({
                    "title": page_info.get("title", "").replace("File:", ""),
                    "url": url,
                    "duration_sec": info.get("duration", 30) or 30,
                    "platform": "wikimedia",
                    "description": "",
                    "thumbnail": info.get("thumburl", ""),
                    "width": info.get("width", 640),
                    "height": info.get("height", 480),
                    "type": "video",
                })

            logger.info("Wikimedia: %d videos for '%s'", len(results), query[:50])
            return results[:max_results]

        except Exception:
            logger.exception("Wikimedia video search failed for '%s'", query)
            return []

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
