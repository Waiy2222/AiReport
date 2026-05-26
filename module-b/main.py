"""Module B — AI 内容加工 (:8002)"""
import os
import uuid
import logging
from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_pool, init_db, close_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [B] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Module B - AI Content Processor")


@app.on_event("startup")
async def startup():
    try:
        await init_db()
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown():
    await close_db()


class ProcessRequest(BaseModel):
    type: str  # morning / evening
    date: str  # YYYY-MM-DD
    batch_id: str


@app.get("/health")
async def health():
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception:
        return {"status": "ok", "db": "disconnected"}


def _get_pool_or_503():
    try:
        return get_pool()
    except RuntimeError:
        raise HTTPException(503, "database not initialized")


@app.post("/run-b")
async def run_b(req: ProcessRequest):
    if req.type not in ("morning", "evening"):
        raise HTTPException(400, "type must be morning or evening")
    briefing_date = date.fromisoformat(req.date)
    batch_id = uuid.UUID(req.batch_id)

    pool = _get_pool_or_503()

    from ai.pipeline import run_pipeline

    logger.info("Starting pipeline: type=%s date=%s batch=%s",
                req.type, req.date, req.batch_id)

    result = await run_pipeline(
        pool=pool,
        batch_id=str(batch_id),
        briefing_type=req.type,
        briefing_date=briefing_date,
    )

    logger.info("Pipeline complete: %s", result.get("stats"))
    return result
