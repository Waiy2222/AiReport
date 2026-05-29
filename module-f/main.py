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

import logging
import uuid
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pipeline import VideoPipeline

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


class GenerateResponse(BaseModel):
    video_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    video_id: str
    status: str
    title: str | None
    output_path: str | None
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
        vid = await pipeline.start(video_id, req.type, gen_date)
    except Exception:
        logger.exception("Failed to start video generation")
        raise HTTPException(500, "failed to start video generation")

    return GenerateResponse(
        video_id=vid["id"],
        status=vid["status"],
        message=f"video generation {vid['status']} — poll /status/{video_id} for updates",
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

    return StatusResponse(**info)


@app.get("/videos")
async def list_videos(limit: int = 10, offset: int = 0):
    """List recent videos."""
    if pipeline is None:
        raise HTTPException(503, "video pipeline not ready")
    return await pipeline.list_videos(limit, offset)
