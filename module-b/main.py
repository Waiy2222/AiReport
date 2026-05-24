"""Module B — AI 内容加工 (:8002)"""
import os
import uuid
from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_pool, init_db, close_db

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

    # TODO: 组员B实现完整 AI 加工流水线:
    #   1. 从 raw_items 读取指定 batch 的数据
    #   2. DeepSeek 评分 (ai_score)
    #   3. 过滤低分 (threshold >= 6)
    #   4. AI 去重 (cross-source + topic dedup)
    #   5. 背景补充 (enrich)
    #   6. 生成 tl_dr / sections / key_takeaways
    #   7. INSERT INTO briefings

    stats = {
        "fetched": 0,
        "scored": 0,
        "passed": 0,
        "dedup_removed": 0,
        "final_count": 0,
    }

    briefing_id = uuid.uuid4()

    return {
        "status": "ok",
        "briefing_id": str(briefing_id),
        "stats": stats,
    }
