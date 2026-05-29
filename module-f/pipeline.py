"""Video generation pipeline — orchestrates all steps.

Leader (E5 skeleton): wires up async flow, DB integration, status tracking.
Team member D fills in: search, download, Gemini analysis, script generation,
FFmpeg editing, TTS, subtitles — the actual media processing logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timezone
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
    """Orchestrates the full video generation workflow."""

    def __init__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.searcher = VideoSearcher()
        self.gemini = GeminiClient()
        self.tts = TTSEngine()
        self.subtitle = SubtitleGenerator()
        self.editor = VideoEditor()
        self._pool: asyncpg.Pool | None = None
        self._tasks: dict[str, asyncio.Task] = {}

    # ---- public API ---------------------------------------------------

    async def start(self, video_id: str, vtype: str, vdate: date) -> dict[str, Any]:
        """Insert a pending record and launch background processing.

        Returns immediately with video_id + status='processing'.
        Poll /status/{video_id} for progress.
        """
        pool = await self._get_pool()

        # Check for existing entry (UNIQUE on type, date)
        existing = await pool.fetchrow(
            "SELECT id, status FROM videos WHERE type = $1 AND date = $2",
            vtype, vdate,
        )
        if existing:
            vid = str(existing["id"])
            if existing["status"] in ("pending", "processing"):
                return {
                    "id": vid,
                    "status": existing["status"],
                    "type": vtype,
                    "date": vdate.isoformat(),
                }
            # Re-generate: delete old and continue
            await pool.execute("DELETE FROM videos WHERE id = $1", existing["id"])

        await pool.execute(
            """INSERT INTO videos (id, type, date, status)
               VALUES ($1, $2, $3, 'processing')""",
            video_id, vtype, vdate,
        )

        # Launch background task
        task = asyncio.create_task(
            self._run_and_catch(video_id, vtype, vdate)
        )
        self._tasks[video_id] = task

        return {
            "id": video_id,
            "status": "processing",
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

        result = dict(row)
        # Convert non-serializable types
        for key in ("date", "created_at", "finished_at"):
            val = result.get(key)
            if isinstance(val, (date, datetime)):
                result[key] = val.isoformat()
        return result

    async def list_videos(self, limit: int = 10, offset: int = 0) -> list[dict]:
        """List recent videos."""
        pool = await self._get_pool()
        rows = await pool.fetch(
            "SELECT * FROM videos ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
        results = []
        for r in rows:
            d = dict(r)
            for key in ("date", "created_at", "finished_at"):
                val = d.get(key)
                if isinstance(val, (date, datetime)):
                    d[key] = val.isoformat()
            results.append(d)
        return results

    # ---- background task wrapper --------------------------------------

    async def _run_and_catch(self, video_id: str, vtype: str, vdate: date):
        """Wrap run_full_pipeline with error handling and DB status update."""
        try:
            output_path = await self.run_full_pipeline(video_id, vtype, vdate)
            pool = await self._get_pool()
            await pool.execute(
                """UPDATE videos SET status = 'done', output_path = $1,
                   finished_at = now() WHERE id = $2""",
                output_path, video_id,
            )
            logger.info("Video %s completed: %s", video_id, output_path)
        except Exception as e:
            logger.exception("Video %s failed", video_id)
            pool = await self._get_pool()
            await pool.execute(
                """UPDATE videos SET status = 'failed', error_msg = $1,
                   finished_at = now() WHERE id = $2""",
                str(e)[:500], video_id,
            )
        finally:
            self._tasks.pop(video_id, None)

    # ---- full pipeline (orchestration skeleton) -----------------------

    async def run_full_pipeline(self, video_id: str, vtype: str, vdate: date) -> str:
        """Execute the complete video generation pipeline.

        Steps 1-8 orchestrated here.  Individual step implementations
        are filled in by team member D.

        Returns the output file path.
        """
        pool = await self._get_pool()
        video_dir = OUTPUT_DIR / video_id
        video_dir.mkdir(parents=True, exist_ok=True)

        # ---- Step 1: Search for clips --------------------------------
        logger.info("[F:%s] Step 1: searching clips", video_id)
        clips = await self.searcher.search("AI agent technology news", max_results=10)

        # ---- Step 2: Download clips ----------------------------------
        logger.info("[F:%s] Step 2: downloading %d clips", video_id, len(clips))
        local_clips: list[str] = []
        for i, clip in enumerate(clips):
            try:
                path = await self.searcher.download(clip["url"])
                if path:
                    local_clips.append(path)
            except NotImplementedError:
                logger.info("[F:%s] Download not implemented — using %d search results as placeholder", video_id, len(clips))
                break
            except Exception as e:
                logger.warning("[F:%s] Clip %d download failed: %s", video_id, i, e)

        # ---- Step 3: Gemini analysis ---------------------------------
        logger.info("[F:%s] Step 3: analyzing clips with Gemini", video_id)
        analyzed: list[dict[str, Any]] = []
        for clip_path in local_clips[:5]:
            try:
                result = await self.gemini.analyze_video(clip_path)
                if result:
                    analyzed.append({**result, "path": clip_path})
            except NotImplementedError:
                logger.info("[F:%s] Gemini analysis not implemented — using mock", video_id)
                analyzed = [
                    {"path": p, "summary": f"Clip {i}", "topics": ["AI"],
                     "relevance_score": 7.0, "suggested_clip_range": {"start_sec": 0, "end_sec": 30}}
                    for i, p in enumerate(local_clips[:3])
                ]
                break
            except Exception as e:
                logger.warning("[F:%s] Gemini analysis failed for %s: %s", video_id, clip_path, e)

        if not analyzed:
            analyzed = [
                {"path": "", "summary": "AI News Highlights", "topics": ["AI"],
                 "relevance_score": 7.0, "suggested_clip_range": {"start_sec": 0, "end_sec": 30}}
            ]

        # ---- Step 4: Select best clips -------------------------------
        logger.info("[F:%s] Step 4: selecting best clips", video_id)
        selected = await self.gemini.select_best_clips(analyzed, max_duration_sec=300)

        # ---- Step 5: Generate script (DeepSeek) ----------------------
        logger.info("[F:%s] Step 5: generating script", video_id)
        script_text = await self._generate_script(vtype, vdate, selected)

        # ---- Step 6: Edit video (FFmpeg concat) ----------------------
        logger.info("[F:%s] Step 6: editing video", video_id)
        raw_video = str(video_dir / "raw_edit.mp4")
        clip_paths = [c.get("path", "") for c in selected if c.get("path")]
        if clip_paths:
            self.editor.concat(clip_paths, raw_video)
        else:
            # No clips downloaded — create placeholder
            logger.warning("[F:%s] No clips available for edit", video_id)

        # ---- Step 7: TTS voiceover -----------------------------------
        logger.info("[F:%s] Step 7: generating voiceover", video_id)
        audio_path = str(video_dir / "voiceover.mp3")
        await self.tts.generate(script_text, audio_path)

        # ---- Step 8: Subtitles & final composite ---------------------
        logger.info("[F:%s] Step 8: subtitles & composite", video_id)
        final_path = str(video_dir / f"{vtype}_{vdate.isoformat()}.mp4")

        # Write a placeholder output for now (team member D completes)
        placeholder = video_dir / "PLACEHOLDER.txt"
        placeholder.write_text(
            f"Video pipeline skeleton executed.\n"
            f"video_id={video_id}\n"
            f"type={vtype}\n"
            f"date={vdate}\n"
            f"clips_found={len(clips)}\n"
            f"clips_analyzed={len(analyzed)}\n"
            f"script_length={len(script_text)} chars\n"
            f"\nTeam member D: implement Steps 2,3,5,6,7,8 in full.\n",
            encoding="utf-8",
        )

        # Save script to DB for reference
        await pool.execute(
            """UPDATE videos SET script = $1, title = $2,
               metadata = $3 WHERE id = $4""",
            script_text,
            f"AI Agent Weekly — {vdate.isoformat()}",
            json.dumps({
                "clips_found": len(clips),
                "clips_analyzed": len(analyzed),
                "selected": len(selected),
                "model": "qwen-vl-max (bailian)",
                "tts": "edge-tts",
            }),
            video_id,
        )

        return final_path

    # ---- internal helpers --------------------------------------------

    async def _generate_script(
        self, vtype: str, vdate: date, clips: list[dict]
    ) -> str:
        """Generate narration script (placeholder — team member D implements DeepSeek call)."""
        topics = set()
        for c in clips:
            for t in c.get("topics", []):
                topics.add(t)

        return (
            f"# AI Agent Weekly — {vdate.isoformat()}\n\n"
            f"欢迎收看本期AI智能体周报。\n\n"
            f"本期主题：{', '.join(sorted(topics)) if topics else 'AI技术前沿'}。\n\n"
            f"（完整脚本由 Module F DeepSeek 调用生成 — 组员 D 实现）\n"
        )

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        return self._pool
