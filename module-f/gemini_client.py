"""Gemini 2.5 Pro API wrapper for video understanding.

Analyzes video clips: describes content, identifies topics, assesses
relevance to AI/agent domain, and suggests edit points.
"""

from __future__ import annotations

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

    async def analyze_video(
        self,
        video_path: str,
        context: str = "",
    ) -> dict[str, Any] | None:
        """Analyze a video clip for content, topics, and quality.

        Returns dict with keys: summary, topics, relevance_score (0-10),
        suggested_clip_range (start_sec, end_sec), quality_notes.
        Returns None if Gemini is not configured or call fails.
        """
        if not self._configured:
            logger.warning("Gemini API key not configured — using mock analysis")
            return self._mock_result(video_path, context)

        # TODO: implement actual Gemini API call
        # import google.generativeai as genai
        # genai.configure(api_key=GEMINI_API_KEY)
        # model = genai.GenerativeModel(GEMINI_MODEL)
        # ...
        raise NotImplementedError(
            "Gemini API integration pending — install google-generativeai"
        )

    async def select_best_clips(
        self,
        clips: list[dict[str, Any]],
        max_duration_sec: int = 300,
    ) -> list[dict[str, Any]]:
        """Select the best subset of clips for a coherent video under max duration."""
        if not self._configured:
            # Return top-scored clips under duration budget
            sorted_clips = sorted(
                clips,
                key=lambda c: c.get("relevance_score", 5),
                reverse=True,
            )
            result = []
            total = 0
            for c in sorted_clips:
                dur = c.get("duration_sec", 30)
                if total + dur <= max_duration_sec:
                    result.append(c)
                    total += dur
            return result

        raise NotImplementedError("Gemini clip selection pending")

    # ---- mock / fallback ----------------------------------------------

    def _mock_result(self, path: str, context: str) -> dict[str, Any]:
        return {
            "video_path": path,
            "summary": f"AI-related clip from {os.path.basename(path)}",
            "topics": ["AI", "agent"],
            "relevance_score": 7.5,
            "suggested_clip_range": {"start_sec": 0, "end_sec": 30},
            "quality_notes": "Good quality, clear visuals",
            "context_match": bool(context),
        }
