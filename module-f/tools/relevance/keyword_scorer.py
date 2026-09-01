"""LLM-powered keyword extraction for B-roll search.

Replaces the hand-maintained 200+ line Chinese→English keyword mapping tables
in video_search.py (_to_pexels_query, _to_youtube_query) with intelligent,
per-news-item keyword generation.

Uses DeepSeek (already configured) to extract:
- Main entity (company/product/person) in Chinese AND English
- Search keywords optimized for each platform (Pexels/YouTube/B站)
- Domain tags for relevance filtering
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import re
from typing import Any

import openai

logger = logging.getLogger(__name__)

# Cache extracted keywords to avoid repeated LLM calls for the same topic
_keyword_cache: dict[str, dict] = {}

EXTRACTION_PROMPT = """Extract search keywords from this Chinese tech news headline for finding B-roll footage. Return ONLY valid JSON, no other text.

News: {topic}

Output JSON format:
{{
  "entity_cn": "公司/产品/人物的中文名",
  "entity_en": "Company/product/person name in English",
  "search_cn": ["中文搜索词1", "中文搜索词2"],
  "search_en": ["english keyword1", "english keyword2"],
  "tags": ["标签1", "标签2"]
}}

Rules:
- entity_cn: The MAIN subject (company name, product name). If unclear, use the most specific noun phrase. Keep it SHORT (2-6 chars).
- entity_en: English equivalent of the main subject. Use official English name if known.
- search_cn: 2-4 Chinese keywords for B站/Pexels search, ordered by specificity. Include entity + category + action words.
- search_en: 2-3 English keywords for YouTube/Pexels search. Use concrete terms, not generic ones like "technology".
- tags: 1-3 from [LLM, Agent, 开源, 工具, 科技, 芯片, 机器人, 自动驾驶, 融资, 安全, 医疗, 行业, 全球, 体育]
- Never use generic keywords like "AI technology news" or "科技新闻"
- Keep it CONCISE. Each keyword should be useful for actual video/image search.
"""


class KeywordExtractor:
    """Extract precise search keywords from news headlines using LLM.

    Usage::

        extractor = KeywordExtractor()
        kw = await extractor.extract("腾讯云ADP 4.0海外版发布，支持MCP协议")
        # kw = {
        #   "entity_cn": "腾讯云",
        #   "entity_en": "Tencent Cloud",
        #   "search_cn": ["腾讯云 ADP", "AI开发平台", "MCP协议"],
        #   "search_en": ["Tencent Cloud ADP", "AI agent platform"],
        #   "tags": ["Agent", "科技", "开源"]
        # }
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY not set — KeywordExtractor disabled")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def extract(self, topic: str, text: str = "") -> dict[str, Any]:
        """Extract search keywords from a news topic.

        Results are cached — same topic returns cached result instantly.
        """
        cache_key = topic[:80]
        if cache_key in _keyword_cache:
            return _keyword_cache[cache_key]

        if not self.available:
            return self._fallback_extract(topic)

        # Combine topic + first sentence of text for context
        context = topic
        if text:
            first_sent = text.split("。")[0][:120]
            if first_sent and first_sent != topic:
                context = f"{topic}。{first_sent}"

        try:
            client = openai.AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
            response = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(topic=context)}],
                temperature=0.3,  # low temp for consistent extraction
                max_tokens=300,
            )
            raw = response.choices[0].message.content or "{}"

            # Extract JSON from response (robust against markdown wrappers)
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                result = _json.loads(json_match.group())
            else:
                result = _json.loads(raw)

            # Validate required fields
            result.setdefault("entity_cn", "")
            result.setdefault("entity_en", "")
            result.setdefault("search_cn", [])
            result.setdefault("search_en", [])
            result.setdefault("tags", [])

            _keyword_cache[cache_key] = result
            logger.info("KeywordExtract: '%s' -> entity=%s/%s cn=%d en=%d tags=%s",
                        topic[:40], result["entity_cn"], result["entity_en"],
                        len(result["search_cn"]), len(result["search_en"]),
                        result["tags"])
            return result

        except Exception as e:
            logger.warning("KeywordExtract LLM failed: %s, using fallback", e)
            return self._fallback_extract(topic)

    def _fallback_extract(self, topic: str) -> dict[str, Any]:
        """Regex-based fallback when LLM is unavailable."""
        # Extract Chinese entity (2-4 char proper nouns)
        cn_words = re.findall(r'[一-鿿]{2,4}', topic)
        # Extract English entity
        en_words = re.findall(r'[A-Z][A-Za-z0-9]{2,}', topic)

        # Remove stop words
        stop = {"科技", "技术", "发布", "正式", "宣布", "今天", "最新",
                "智能体", "人工智能", "新闻", "推出", "上线"}
        cn_filtered = [w for w in cn_words if w not in stop]

        return {
            "entity_cn": cn_filtered[0] if cn_filtered else "",
            "entity_en": en_words[0] if en_words else "",
            "search_cn": cn_filtered[:4],
            "search_en": en_words[:3] if en_words else ["AI technology"],
            "tags": [],
        }

    async def extract_batch(
        self, topics: list[tuple[str, str]]
    ) -> list[dict[str, Any]]:
        """Extract keywords for multiple topics concurrently."""
        tasks = [self.extract(topic, text) for topic, text in topics]
        return await asyncio.gather(*tasks)


# ── Integration helper: convert extracted keywords to search queries ──

def keywords_to_queries(kw: dict) -> dict[str, str]:
    """Convert extracted keywords to platform-optimized search queries.

    Returns dict with keys: bilibili, youtube, pexels, image_en, image_cn
    """
    entity_cn = kw.get("entity_cn", "")
    entity_en = kw.get("entity_en", "")
    search_cn = kw.get("search_cn", [])
    search_en = kw.get("search_en", [])

    return {
        "bilibili": " ".join([entity_cn] + search_cn[:2]) if entity_cn else " ".join(search_cn[:3]),
        "youtube": " ".join([entity_en] + search_en[:2]) if entity_en else " ".join(search_en[:3]),
        "pexels": " ".join(search_en[:3]) if search_en else "technology",
        "image_en": " ".join(search_en[:2]) if search_en else entity_en or "technology",
        "image_cn": " ".join([entity_cn] + search_cn[:2]) if entity_cn else " ".join(search_cn[:3]),
    }
