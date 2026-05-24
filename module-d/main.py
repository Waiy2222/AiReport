"""Module D — 多平台发布 (:8004)"""
import json
import os
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_pool, init_db, close_db

app = FastAPI(title="Module D - Multi-Platform Publisher")

PLATFORMS = ["zhihu", "csdn", "weixin_oa"]

# asyncpg 将 JSONB 列返回为 Python 字符串，需手动解析
_JSONB_FIELDS = {"tl_dr", "sections", "key_takeaways", "raw_stats"}


def _parse_briefing(row) -> dict:
    """将 asyncpg Record 转为 dict，并解析 JSONB 字符串字段"""
    briefing = dict(row)
    for field in _JSONB_FIELDS:
        val = briefing.get(field)
        if isinstance(val, str):
            try:
                briefing[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass  # 保持原值
    return briefing


@app.on_event("startup")
async def startup():
    try:
        await init_db()
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown():
    await close_db()


class PublishRequest(BaseModel):
    briefing_id: str
    platforms: list[str] = ["zhihu", "csdn", "weixin_oa"]


@app.get("/health")
async def health():
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception:
        return {"status": "ok", "db": "disconnected"}


@app.post("/publish")
async def publish(req: PublishRequest):
    briefing_id = uuid.UUID(req.briefing_id)

    for p in req.platforms:
        if p not in PLATFORMS:
            raise HTTPException(400, f"unsupported platform: {p}")

    pool = get_pool()

    # 读取完整简报数据（JSONB 字段需解析）
    row = await pool.fetchrow(
        "SELECT * FROM briefings WHERE id=$1", briefing_id
    )
    if not row:
        raise HTTPException(404, "briefing not found")
    briefing = _parse_briefing(row)

    # 通过 orchestrator 并发发布
    from orchestrator import publish_all
    results = await publish_all(pool, briefing_id, briefing, req.platforms)

    return {
        "briefing_id": str(briefing_id),
        "results": results,
    }
