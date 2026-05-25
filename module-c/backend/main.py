"""Module C — 微信小程序后端 (:8003)

无 PostgreSQL 时自动使用内置假数据，无需任何外部依赖即可运行。
"""
import os
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query

from db import get_pool, init_db, close_db
from models import SubscribeRequest, UnsubscribeRequest, PushRequest
from mock_data import get_briefings, get_subscriptions

app = FastAPI(title="Module C - WeChat Mini Program Backend")

# 数据库是否可用
_db_ok = False


@app.on_event("startup")
async def startup():
    global _db_ok
    try:
        await init_db()
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        _db_ok = True
        print("[module-c] PostgreSQL connected")
    except Exception:
        _db_ok = False
        print("[module-c] PostgreSQL not available, using mock data")


@app.on_event("shutdown")
async def shutdown():
    await close_db()


def _db():
    """获取数据库连接，如果不可用则抛错"""
    if not _db_ok:
        raise RuntimeError("db unavailable")
    return get_pool()


# ── /health ──────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "db": "connected" if _db_ok else "mock"}


# ── /api/briefings/latest ────────────────────────────────────────
@app.get("/api/briefings/latest")
async def get_latest(type: str = Query(..., description="morning or evening")):
    if type not in ("morning", "evening"):
        raise HTTPException(400, "type must be morning or evening")

    try:
        pool = _db()
        row = await pool.fetchrow(
            "SELECT * FROM briefings WHERE type=$1 ORDER BY date DESC LIMIT 1", type
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
    except RuntimeError:
        all_briefings = get_briefings()
        for b in all_briefings:
            if b["type"] == type:
                return b
        raise HTTPException(404, "no briefing found")


# ── /api/briefings/history ───────────────────────────────────────
@app.get("/api/briefings/history")
async def get_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="搜索关键词"),
):
    try:
        pool = _db()
        offset = (page - 1) * size
        if keyword:
            rows = await pool.fetch(
                """SELECT id, type, date, tl_dr, generated_at FROM briefings
                   WHERE tl_dr::text ILIKE $1
                   ORDER BY date DESC OFFSET $2 LIMIT $3""",
                f"%{keyword}%", offset, size,
            )
            total = await pool.fetchval(
                "SELECT COUNT(*) FROM briefings WHERE tl_dr::text ILIKE $1",
                f"%{keyword}%",
            )
        else:
            rows = await pool.fetch(
                "SELECT id, type, date, tl_dr, generated_at FROM briefings ORDER BY date DESC OFFSET $1 LIMIT $2",
                offset, size,
            )
            total = await pool.fetchval("SELECT COUNT(*) FROM briefings")

        items = [
            {
                "id": str(r["id"]),
                "type": r["type"],
                "date": str(r["date"]),
                "tl_dr": r["tl_dr"],
                "generated_at": r["generated_at"].isoformat(),
            }
            for r in rows
        ]
    except RuntimeError:
        all_briefings = get_briefings()
        if keyword:
            all_briefings = [
                b for b in all_briefings
                if keyword.lower() in str(b["tl_dr"]).lower()
            ]
        total = len(all_briefings)
        start = (page - 1) * size
        end = start + size
        items = [
            {
                "id": b["id"],
                "type": b["type"],
                "date": b["date"],
                "tl_dr": b["tl_dr"],
                "generated_at": b["generated_at"],
            }
            for b in all_briefings[start:end]
        ]

    return {"page": page, "size": size, "total": total, "items": items}


# ── /api/briefings/{briefing_id} ─────────────────────────────────
@app.get("/api/briefings/{briefing_id}")
async def get_briefing_detail(briefing_id: str):
    try:
        UUID(briefing_id)
    except ValueError:
        raise HTTPException(400, "invalid briefing id format")

    try:
        pool = _db()
        row = await pool.fetchrow(
            "SELECT * FROM briefings WHERE id=$1", UUID(briefing_id),
        )
        if not row:
            raise HTTPException(404, "briefing not found")
        return {
            "id": str(row["id"]),
            "type": row["type"],
            "date": str(row["date"]),
            "language": row["language"],
            "tl_dr": row["tl_dr"],
            "sections": row["sections"],
            "key_takeaways": row["key_takeaways"],
            "raw_stats": row["raw_stats"],
            "generated_at": row["generated_at"].isoformat(),
        }
    except RuntimeError:
        for b in get_briefings():
            if b["id"] == briefing_id:
                return b
        raise HTTPException(404, "briefing not found")


# ── /api/subscribe ───────────────────────────────────────────────
@app.post("/api/subscribe")
async def subscribe(req: SubscribeRequest):
    try:
        pool = _db()
        await pool.execute(
            """INSERT INTO subscriptions (openid, morning_enabled, evening_enabled)
               VALUES ($1, $2, $3)
               ON CONFLICT (openid) DO UPDATE SET
                 subscribed=true, morning_enabled=$2, evening_enabled=$3""",
            req.openid, req.morning_enabled, req.evening_enabled,
        )
    except RuntimeError:
        pass
    return {"status": "ok", "openid": req.openid}


# ── /api/unsubscribe ─────────────────────────────────────────────
@app.post("/api/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest):
    try:
        pool = _db()
        await pool.execute(
            "UPDATE subscriptions SET subscribed=false WHERE openid=$1",
            req.openid,
        )
    except RuntimeError:
        pass
    return {"status": "ok", "openid": req.openid}


# ── /push ────────────────────────────────────────────────────────
@app.post("/push")
async def push(req: PushRequest):
    # 简报
    try:
        UUID(req.briefing_id)
    except ValueError:
        raise HTTPException(400, "invalid briefing id format")

    try:
        pool = _db()
        briefing_row = await pool.fetchrow(
            "SELECT id, type, date, tl_dr FROM briefings WHERE id=$1",
            UUID(req.briefing_id),
        )
        if not briefing_row:
            raise HTTPException(404, "briefing not found")
        briefing = {
            "id": str(briefing_row["id"]),
            "type": briefing_row["type"],
            "date": str(briefing_row["date"]),
            "tl_dr": briefing_row["tl_dr"],
        }
        subscribers = await pool.fetch(
            "SELECT openid, morning_enabled, evening_enabled FROM subscriptions WHERE subscribed=true"
        )
        targets = [
            {"openid": s["openid"], "morning_enabled": s["morning_enabled"], "evening_enabled": s["evening_enabled"]}
            for s in subscribers
        ]
    except RuntimeError:
        # Mock 模式
        briefing = next((b for b in get_briefings() if b["id"] == req.briefing_id), None)
        if not briefing:
            raise HTTPException(404, "briefing not found")
        targets = get_subscriptions()

    btype = briefing["type"]
    targets = [
        t for t in targets
        if (btype == "morning" and t.get("morning_enabled", True))
        or (btype == "evening" and t.get("evening_enabled", True))
    ]

    if not os.getenv("WX_APPID"):
        return {
            "status": "dry_run",
            "briefing_id": req.briefing_id,
            "total": len(targets),
            "success": 0,
            "failed": 0,
            "detail": [{"openid": t["openid"], "result": "dry_run"} for t in targets],
        }

    from push import batch_push
    result = await batch_push(briefing, targets)
    return result
