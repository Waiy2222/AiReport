"""Module B — AI 内容加工 (:8002)"""
import json
import uuid
import logging
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from db import get_pool, init_db, close_db
from pipeline import run_pipeline
from ai.render_longimage import render_longimage

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


def _parse_jsonb(val) -> list | dict:
    """解析 PostgreSQL JSONB 字段（可能是 str 或已解析的 list/dict）"""
    if isinstance(val, str):
        return json.loads(val)
    return val


@app.get("/longimage/{briefing_id}")
async def longimage(briefing_id: str):
    """生成简报长图 PNG"""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, type, date, tl_dr, sections, key_takeaways, raw_stats "
            "FROM briefings WHERE id = $1",
            uuid.UUID(briefing_id),
        )
    if not row:
        raise HTTPException(404, "briefing not found")

    tl_dr = _parse_jsonb(row["tl_dr"])
    sections = _parse_jsonb(row["sections"])
    key_takeaways = _parse_jsonb(row["key_takeaways"])
    raw_stats = _parse_jsonb(row["raw_stats"])

    # headline 存储在 raw_stats 中（DB 表无独立 headline 列）
    headline = raw_stats.get("headline", {}) if isinstance(raw_stats, dict) else {}

    briefing = {
        "headline": headline,
        "tl_dr": tl_dr,
        "sections": sections,
        "key_takeaways": key_takeaways,
    }

    png_bytes = await render_longimage(briefing, row["type"], str(row["date"]), raw_stats)
    return Response(content=png_bytes, media_type="image/png")
