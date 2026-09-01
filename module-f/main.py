"""Module F — AI视频生成 (:8006)

Capabilities:
- Search and download AI/agent-related video clips from the web
- Analyze clips with Gemini 2.5 Pro (multimodal understanding)
- Generate scripts with DeepSeek
- Edit/concatenate with FFmpeg
- AI voiceover with Edge TTS
- Subtitles with Whisper

All generation is unified (not per-user).  Output saved locally, not pushed.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date
from pathlib import Path

# Load .env.local if it exists (auto-loads API keys without shell env vars)
_env_local = Path(__file__).parent / ".env.local"
if _env_local.exists():
    with open(_env_local, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                if key and val and key not in os.environ:
                    os.environ[key] = val
    logging.info("Loaded env from .env.local")

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline import VideoPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [F:%(name)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Module F - Video Generator")

pipeline: VideoPipeline | None = None


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup():
    global pipeline
    try:
        pipeline = VideoPipeline()
        logger.info("Module F started")
    except Exception:
        logger.exception("Module F startup failed")
        raise


@app.on_event("shutdown")
async def shutdown():
    logger.info("Module F stopped")


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    type: str = "ai_agent_weekly"
    date: str | None = None  # defaults to today
    keyword: str | None = None  # custom topic keyword (e.g. "新能源", "量子计算")


class GenerateResponse(BaseModel):
    video_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    video_id: str
    status: str
    title: str | None
    output_path: str | None
    cover_path: str | None
    duration_seconds: int | None
    error_msg: str | None
    metadata: dict | None


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """Kick off video generation (launches background task, returns immediately)."""
    if pipeline is None:
        raise HTTPException(503, "video pipeline not ready")

    gen_date = (
        date.fromisoformat(req.date)
        if req.date
        else date.today()
    )

    video_id = str(uuid.uuid4())

    try:
        vid = await pipeline.start(video_id, req.type, gen_date, keyword=req.keyword)
    except Exception:
        logger.exception("Failed to start video generation")
        raise HTTPException(500, "failed to start video generation")

    actual_id = vid["id"]
    return GenerateResponse(
        video_id=actual_id,
        status=vid["status"],
        message=f"video generation {vid['status']} — poll /status/{actual_id} for updates",
    )


@app.get("/status/{video_id}", response_model=StatusResponse)
async def get_status(video_id: str):
    """Check video generation progress."""
    if pipeline is None:
        raise HTTPException(503, "video pipeline not ready")

    try:
        info = await pipeline.status(video_id)
    except Exception:
        raise HTTPException(404, f"video not found: {video_id}")

    # Map DB fields to StatusResponse model
    meta = info.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = None

    return StatusResponse(
        video_id=str(info.get("id", video_id)),
        status=info.get("status", "unknown"),
        title=info.get("title"),
        output_path=info.get("output_path"),
        cover_path=meta.get("cover_path", "") if isinstance(meta, dict) else None,
        duration_seconds=info.get("duration_seconds"),
        error_msg=info.get("error_msg"),
        metadata=meta if isinstance(meta, dict) else None,
    )


@app.get("/cover/{video_id}")
async def get_cover(video_id: str):
    """Serve the cover/thumbnail image for a video."""
    if pipeline is None:
        raise HTTPException(503, "video pipeline not ready")

    try:
        info = await pipeline.status(video_id)
    except Exception:
        raise HTTPException(404, f"video not found: {video_id}")

    meta = info.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}

    cover_path = meta.get("cover_path", "") if isinstance(meta, dict) else ""
    if not cover_path or not Path(cover_path).exists():
        raise HTTPException(404, "cover not available for this video")

    return FileResponse(cover_path, media_type="image/jpeg")


@app.get("/videos")
async def list_videos(limit: int = 10, offset: int = 0):
    """List recent videos."""
    if pipeline is None:
        raise HTTPException(503, "video pipeline not ready")
    return await pipeline.list_videos(limit, offset)
