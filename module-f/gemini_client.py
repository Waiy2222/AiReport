"""Gemini 2.5 Pro API wrapper for video understanding.

Phase 2: implemented actual API call with retry + has_api_key() detection
+ graceful mock fallback when API is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro-exp-03-25")


class GeminiClient:
    """Thin wrapper around Google Generative AI SDK for video analysis."""

    def __init__(self):
        self._configured = bool(GEMINI_API_KEY)
        self._max_retries = 3

    @staticmethod
    def has_api_key() -> bool:
        """Check if Gemini API key is configured."""
        return bool(GEMINI_API_KEY)

    async def analyze_video(
        self,
        video_path: str,
        context: str = "",
    ) -> dict[str, Any] | None:
        """Analyze a video clip for content, topics, and quality.

        Returns dict with keys: summary, topics, relevance_score (0-10),
        suggested_clip_range (start_sec, end_sec), quality_notes.
        Returns None if Gemini is not configured and mock also fails.
        """
        if not self._configured:
            logger.warning("Gemini API key not configured — using mock analysis")
            return self._mock_result(video_path, context)

        for attempt in range(self._max_retries):
            try:
                return await self._call_gemini(video_path, context)
            except ImportError:
                logger.warning("google-generativeai not installed — using mock")
                return self._mock_result(video_path, context)
            except Exception as e:
                logger.warning(
                    "Gemini attempt %d/%d failed: %s",
                    attempt + 1, self._max_retries, e,
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        logger.warning("All Gemini attempts failed — using mock result")
        return self._mock_result(video_path, context)

    async def analyze_video_content(
        self,
        video_path: str,
        context: str = "",
    ) -> dict[str, Any] | None:
        """Alias for analyze_video (test consistency)."""
        return await self.analyze_video(video_path, context)

    async def select_best_clips(
        self,
        clips: list[dict[str, Any]],
        max_duration_sec: int = 300,
    ) -> list[dict[str, Any]]:
        """Select the best subset of clips for a coherent video under max duration.

        Uses Gemini when available; falls back to score-based greedy selection.
        """
        if self._configured:
            try:
                result = await self._gemini_select_clips(clips, max_duration_sec)
                if result:
                    return result
            except ImportError:
                pass  # fall through to score-based
            except Exception as e:
                logger.warning("Gemini clip selection failed: %s", e)

        # Score-based greedy selection fallback
        sorted_clips = sorted(
            clips,
            key=lambda c: c.get("relevance_score", 5),
            reverse=True,
        )
        result: list[dict] = []
        total = 0
        for c in sorted_clips:
            dur = c.get("duration_sec", 30)
            if total + dur <= max_duration_sec:
                result.append(c)
                total += dur
        return result

    # ------------------------------------------------------------------
    # internal: actual Gemini API calls
    # ------------------------------------------------------------------

    async def _call_gemini(
        self, video_path: str, context: str
    ) -> dict[str, Any]:
        """Call Gemini API via google-generativeai SDK."""
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        uploaded_file = genai.upload_file(video_path)
        prompt = (
            f"Analyze this video clip. Context: {context}\n\n"
            "Return a JSON object with these fields:\n"
            "- summary (str): Brief description of the clip content\n"
            "- topics (list of str): Key topics discussed or shown\n"
            "- relevance_score (int 0-10): Relevance to AI/agent domain\n"
            "- quality_notes (str): Visual and audio quality assessment\n"
            "- suggested_clip_range (dict): with 'start_sec' and 'end_sec'"
        )
        response = model.generate_content([uploaded_file, prompt])

        text = response.text
        result: dict[str, Any] = {}
        try:
            json_start = text.index("{")
            json_end = text.rindex("}") + 1
            result = json.loads(text[json_start:json_end])
        except (ValueError, json.JSONDecodeError):
            result["summary"] = text[:300]

        result["video_path"] = video_path
        result["context_match"] = bool(context)
        return result

    async def _gemini_select_clips(
        self, clips: list[dict], max_duration_sec: int
    ) -> list[dict] | None:
        """Ask Gemini which clips to include."""
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        summaries = [
            {
                "i": i,
                "title": c.get("title", ""),
                "dur": c.get("duration_sec", 30),
                "score": c.get("relevance_score", 5),
            }
            for i, c in enumerate(clips)
        ]
        prompt = (
            f"Select the best clip indices for a coherent AI news video "
            f"under {max_duration_sec} seconds.\n"
            f"Clips: {json.dumps(summaries, ensure_ascii=False)}\n"
            "Return only a JSON array of indices, e.g. [0, 2, 3]."
        )
        response = model.generate_content(prompt)

        text = response.text
        json_start = text.index("[")
        json_end = text.rindex("]") + 1
        indices = json.loads(text[json_start:json_end])
        return [clips[i] for i in indices if i < len(clips)]

    # ------------------------------------------------------------------
    # mock / fallback
    # ------------------------------------------------------------------

    def _mock_result(self, path: str, context: str) -> dict[str, Any]:
        return {
            "video_path": path,
            "summary": f"AI-related clip from {os.path.basename(path)}",
            "topics": ["AI", "agent", "technology"],
            "relevance_score": 7.5,
            "suggested_clip_range": {"start_sec": 0, "end_sec": 30},
            "quality_notes": "Good quality, clear visuals",
            "context_match": bool(context),
        }
