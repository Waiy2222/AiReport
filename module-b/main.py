"""Module B — AI 内容加工 (:8002)"""
import uuid
import logging
from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_pool, init_db, close_db
from pipeline import run_pipeline

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


@app.post("/run-b")
async def run_b(req: ProcessRequest):
    if req.type not in ("morning", "evening"):
        raise HTTPException(400, "type must be morning or evening")
    briefing_date = date.fromisoformat(req.date)
    batch_id = uuid.UUID(req.batch_id)

    pool = get_pool()
    result = await run_pipeline(pool, req.type, str(briefing_date), batch_id)

    return {
        "status": "ok",
        "briefing_id": str(result["briefing_id"]),
        "stats": result["stats"],
    }
