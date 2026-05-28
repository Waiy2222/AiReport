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

import asyncio
import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pipeline import VideoPipeline

logger = logging.getLogger(__name__)

app = FastAPI(title="Module F - Video Generator")

pipeline: VideoPipeline | None = None

# Phase 2: DB 连接管理
_db_pool = None
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ai_news")
OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./output")).resolve()
DOWNLOADS_DIR = Path(os.getenv("VIDEO_DOWNLOAD_DIR", "./downloads")).resolve()


# ---------------------------------------------------------------------------
# lifecycle
# ---------------------------------------------------------------------------


async def _init_db():
    """初始化 DB 连接池"""
    global _db_pool
    try:
        import asyncpg
        _db_pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        logger.info("DB connected: %s", DB_URL)
    except Exception as e:
        logger.warning("DB not available (video status won't persist): %s", e)
        _db_pool = None


async def _close_db():
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None


@app.on_event("startup")
async def startup():
    global pipeline
    # Phase 2: 确保输出目录存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    # DB 连接（非阻塞）
    await _init_db()
    try:
        pipeline = VideoPipeline()
        logger.info("Module F started (output=%s, downloads=%s)", OUTPUT_DIR, DOWNLOADS_DIR)
    except Exception:
        logger.exception("Module F startup failed")
        raise


@app.on_event("shutdown")
async def shutdown():
    await _close_db()
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
    title: str | None = None
    output_path: str | None = None
    duration_seconds: int | None = None
    error_msg: str | None = None
    metadata: dict | None = None


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


async def _write_video_record(video_id: str, vtype: str, vdate: date) -> bool:
    """Phase 2: 向 videos 表写入初始记录（status=pending）"""
    if _db_pool is None:
        logger.warning("DB not available, video record not persisted")
        return False
    try:
        async with _db_pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO videos (id, type, date, status, metadata)
                   VALUES ($1::uuid, $2, $3, 'pending', $4::jsonb)
                   ON CONFLICT (type, date) DO NOTHING""",
                uuid.UUID(video_id),
                vtype,
                vdate,
                json.dumps({"started_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False),
            )
        return True
    except Exception as e:
        logger.warning("Failed to write video record: %s", e)
        return False


async def _update_video_status(video_id: str, status: str, **extra):
    """Phase 2: 更新 videos 表状态"""
    if _db_pool is None:
        return
    try:
        sets = ["status = $2"]
        values = [video_id, status]
        idx = 3
        for key, val in extra.items():
            if key == "metadata" and isinstance(val, dict):
                sets.append(f"{key} = ${idx}::jsonb")
                values.append(json.dumps(val, ensure_ascii=False))
            elif key == "finished_at":
                sets.append(f"{key} = ${idx}")
                values.append(val)
            else:
                sets.append(f"{key} = ${idx}")
                values.append(val)
            idx += 1
        async with _db_pool.acquire() as conn:
            await conn.execute(
                f"UPDATE videos SET {', '.join(sets)} WHERE id = $1::uuid",
                *values,
            )
    except Exception as e:
        logger.warning("Failed to update video status: %s", e)


async def _run_pipeline_background(video_id: str, vtype: str, vdate: date):
    """Phase 2: 后台执行完整视频生成流水线"""
    try:
        await _update_video_status(video_id, "processing")
        if pipeline is None:
            raise RuntimeError("pipeline not initialized")
        output_path = await pipeline.run_full_pipeline(video_id, vtype, vdate)
        await _update_video_status(
            video_id,
            "done",
            output_path=output_path,
            finished_at=datetime.now(timezone.utc),
            metadata={
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "output_path": output_path,
            },
        )
    except Exception as e:
        logger.exception("Video pipeline failed")
        await _update_video_status(
            video_id,
            "failed",
            error_msg=str(e),
            finished_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Phase 2: 增强健康检查 — 含 DB + 目录状态"""
    db_status = "connected" if _db_pool else "disconnected"
    output_ok = OUTPUT_DIR.exists()
    downloads_ok = DOWNLOADS_DIR.exists()
    return {
        "status": "ok",
        "db": db_status,
        "output_dir": output_ok,
        "downloads_dir": downloads_ok,
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """Phase 2: 触发视频生成（异步后台执行，立即返回 video_id）"""
    if pipeline is None:
        raise HTTPException(503, "video pipeline not ready")

    gen_date = (
        date.fromisoformat(req.date)
        if req.date
        else date.today()
    )

    video_id = str(uuid.uuid4())

    # Phase 2: 写入 DB
    await _write_video_record(video_id, req.type, gen_date)

    # Phase 2: 启动后台任务（不阻塞 HTTP 响应）
    asyncio.create_task(_run_pipeline_background(video_id, req.type, gen_date))

    return GenerateResponse(
        video_id=video_id,
        status="pending",
        message="video generation started — poll /status/{id} for updates",
    )


@app.get("/status/{video_id}", response_model=StatusResponse)
async def get_status(video_id: str):
    """Phase 2: 从 DB 查询视频生成状态"""
    try:
        uid = uuid.UUID(video_id)
    except ValueError:
        raise HTTPException(400, f"invalid video_id format: {video_id}")

    if _db_pool:
        try:
            row = await _db_pool.fetchrow(
                "SELECT * FROM videos WHERE id = $1::uuid", uid,
            )
            if row:
                return StatusResponse(
                    video_id=str(row["id"]),
                    status=row["status"],
                    title=row.get("title"),
                    output_path=row.get("output_path"),
                    duration_seconds=row.get("duration_seconds"),
                    error_msg=row.get("error_msg"),
                    metadata=row.get("metadata"),
                )
        except Exception as e:
            logger.warning("DB query failed: %s", e)

    raise HTTPException(404, f"video not found: {video_id}")


@app.get("/videos")
async def list_videos(limit: int = 10, offset: int = 0):
    """Phase 2: 从 DB 获取视频列表（无 DB 时返回空列表）"""
    if _db_pool:
        try:
            rows = await _db_pool.fetch(
                "SELECT id, type, date, title, status, output_path, "
                "duration_seconds, error_msg, created_at "
                "FROM videos ORDER BY created_at DESC LIMIT $1 OFFSET $2",
                limit, offset,
            )
            total = await _db_pool.fetchval("SELECT COUNT(*) FROM videos")
            items = []
            for r in rows:
                items.append({
                    "video_id": str(r["id"]),
                    "type": r["type"],
                    "date": str(r["date"]),
                    "title": r["title"],
                    "status": r["status"],
                    "output_path": r["output_path"],
                    "duration_seconds": r["duration_seconds"],
                    "error_msg": r["error_msg"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                })
            return {"total": total, "videos": items}
        except Exception as e:
            logger.warning("DB query failed: %s", e)

    # 无 DB 时返回空
    return {"total": 0, "videos": []}
