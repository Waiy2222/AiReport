"""Module C — 微信小程序后端 (:8003)"""
import os

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from db import get_pool, init_db, close_db

app = FastAPI(title="Module C - WeChat Mini Program Backend")


@app.on_event("startup")
async def startup():
    try:
        await init_db()
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown():
    await close_db()


def _get_pool_or_503():
    try:
        return get_pool()
    except RuntimeError:
        raise HTTPException(503, "database not initialized")


class PushRequest(BaseModel):
    type: str  # morning / evening


@app.get("/health")
async def health():
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception:
        return {"status": "ok", "db": "disconnected"}


@app.post("/push")
async def push(req: PushRequest):
    if req.type not in ("morning", "evening"):
        raise HTTPException(400, "type must be morning or evening")

    # TODO: 组员C实现微信订阅消息推送:
    #   1. 查询 briefings 表获取最新简报
    #   2. 查询 subscriptions 表获取所有已订阅用户
    #   3. 调用微信订阅消息 API 逐用户推送
    #   4. 记录推送结果

    return {"status": "ok", "pushed": 0, "failed": 0}


@app.get("/api/briefings/latest")
async def get_latest(type: str = Query(..., description="morning or evening")):
    if type not in ("morning", "evening"):
        raise HTTPException(400, "type must be morning or evening")

    pool = _get_pool_or_503()
    row = await pool.fetchrow(
        "SELECT * FROM briefings WHERE type=$1 ORDER BY date DESC LIMIT 1",
        type,
    )
    if not row:
        raise HTTPException(404, "no briefing found")

    return {
        "id": str(row["id"]),
        "type": row["type"],
        "date": str(row["date"]),
        "tl_dr": row["tl_dr"],
        "sections": row["sections"],
        "key_takeaways": row["key_takeaways"],
        "generated_at": row["generated_at"].isoformat(),
    }


@app.get("/api/briefings/history")
async def get_history(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    pool = _get_pool_or_503()
    offset = (page - 1) * size
    rows = await pool.fetch(
        "SELECT id, type, date, tl_dr, generated_at FROM briefings ORDER BY date DESC OFFSET $1 LIMIT $2",
        offset, size,
    )
    total = await pool.fetchval("SELECT COUNT(*) FROM briefings")

    return {
        "page": page,
        "size": size,
        "total": total,
        "items": [
            {
                "id": str(r["id"]),
                "type": r["type"],
                "date": str(r["date"]),
                "tl_dr": r["tl_dr"],
                "generated_at": r["generated_at"].isoformat(),
            }
            for r in rows
        ],
    }


class SubscribeRequest(BaseModel):
    openid: str
    morning_enabled: bool = True
    evening_enabled: bool = True


@app.post("/api/subscribe")
async def subscribe(req: SubscribeRequest):
    pool = _get_pool_or_503()
    await pool.execute(
        """INSERT INTO subscriptions (openid, morning_enabled, evening_enabled)
           VALUES ($1, $2, $3)
           ON CONFLICT (openid) DO UPDATE SET
             subscribed=true, morning_enabled=$2, evening_enabled=$3""",
        req.openid, req.morning_enabled, req.evening_enabled,
    )
    return {"status": "ok", "openid": req.openid}


class UnsubscribeRequest(BaseModel):
    openid: str


@app.post("/api/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest):
    pool = _get_pool_or_503()
    result = await pool.execute(
        "UPDATE subscriptions SET subscribed=false WHERE openid=$1",
        req.openid,
    )
    return {"status": "ok", "openid": req.openid}
