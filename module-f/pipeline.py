"""Video generation pipeline — orchestrates all steps."""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import asyncpg

from gemini_client import GeminiClient
from video_search import VideoSearcher
from editor import VideoEditor
from tts import TTSEngine
from subtitle import SubtitleGenerator

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./output")).resolve()
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_news")


class VideoPipeline:
    """Orchestrates the full video generation workflow.

    1. Search/download clips from the web (YouTube etc.)
    2. Analyze each clip with Gemini (what's in it?)
    3. Generate a script with DeepSeek
    4. Edit/concatenate clips with FFmpeg
    5. Add AI voiceover (Edge TTS)
    6. Burn subtitles (Whisper)
    7. Save metadata to ``videos`` table
    """

    def __init__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.searcher = VideoSearcher()
        self.gemini = GeminiClient()
        self.tts = TTSEngine()
        self.subtitle = SubtitleGenerator()
        self.editor = VideoEditor()

    # ---- public API ---------------------------------------------------

    async def start(self, video_id: str, vtype: str, vdate: date) -> dict[str, Any]:
        """Start video generation (non-blocking — TODO: run in background task)."""
        # For now, run synchronously in the HTTP handler's background
        # In production, offload to a task queue (APScheduler / Celery / asyncio.create_task)
        return {
            "id": video_id,
            "status": "pending",
            "type": vtype,
            "date": vdate.isoformat(),
        }

    async def status(self, video_id: str) -> dict[str, Any]:
        """Query video status from DB."""
        pool = await self._get_pool()
        row = await pool.fetchrow(
            "SELECT * FROM videos WHERE id = $1::uuid", video_id
        )
        if row is None:
            raise ValueError(f"video not found: {video_id}")
        return dict(row)

    async def list_videos(self, limit: int = 10, offset: int = 0) -> list[dict]:
        """List recent videos."""
        pool = await self._get_pool()
        rows = await pool.fetch(
            "SELECT * FROM videos ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
        return [dict(r) for r in rows]

    async def run_full_pipeline(self, video_id: str, vtype: str, vdate: date) -> str:
        """Execute the complete pipeline and return output path."""
        # Step 1: Search clips
        # Step 2: Download clips
        # Step 3: Gemini analysis
        # Step 4: DeepSeek script
        # Step 5: FFmpeg edit
        # Step 6: TTS voiceover
        # Step 7: Whisper subtitles
        # Step 8: Final compositing
        raise NotImplementedError("full pipeline not yet implemented — see individual modules")

    # ---- internal -----------------------------------------------------

    _pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            import asyncpg
            self._pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        return self._pool
