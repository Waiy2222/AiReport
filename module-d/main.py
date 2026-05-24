"""Module D — 多平台发布 (:8004)"""
import os
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_pool, init_db, close_db

app = FastAPI(title="Module D - Multi-Platform Publisher")

PLATFORMS = ["zhihu", "csdn", "weixin_oa"]


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

    # 验证简报存在
    briefing = await pool.fetchrow(
        "SELECT id FROM briefings WHERE id=$1", briefing_id
    )
    if not briefing:
        raise HTTPException(404, "briefing not found")

    results = []
    for platform in req.platforms:
        result = await _publish_to(pool, briefing_id, platform)
        results.append(result)

    return {
        "briefing_id": str(briefing_id),
        "results": results,
    }


async def _publish_to(pool, briefing_id: uuid.UUID, platform: str) -> dict:
    # TODO: 组员D实现各平台发布逻辑:
    #   zhihu: 知乎专栏 API
    #   csdn: CSDN 文章 API
    #   weixin_oa: 微信公众号草稿+发布 API
    return {
        "platform": platform,
        "status": "pending",
        "url": None,
        "error": None,
    }
