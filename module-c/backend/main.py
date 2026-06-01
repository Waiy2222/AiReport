"""Module C — 微信小程序+公众号后端 (:8003)

Phase 2 更新：新增公众号回调、标签管理、用户行为追踪、个性化推送。
无 PostgreSQL 时自动使用内置假数据，无需任何外部依赖即可运行。
"""
import json
import os
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles

from db import get_pool, init_db, close_db
from models import SubscribeRequest, UnsubscribeRequest, PushRequest
from mock_data import get_briefings, get_subscriptions

app = FastAPI(title="Module C - WeChat Mini Program + OA Backend")

# 数据库是否可用
_db_ok = False

# 注册 Phase 2 路由模块
from tags import router as tags_router, set_db_pool as set_tags_db_pool
app.include_router(tags_router)


@app.on_event("startup")
async def startup():
    global _db_ok
    try:
        await init_db()
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        _db_ok = True
        set_tags_db_pool(pool)
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


def _get_pool_or_503():
    try:
        return _db()
    except RuntimeError:
        raise HTTPException(503, "database not initialized")


# 静态文件服务（H5 页面）
_h5_dir = os.path.join(os.path.dirname(__file__), "..", "h5")
if os.path.isdir(_h5_dir):
    app.mount("/h5", StaticFiles(directory=_h5_dir, html=True), name="h5")


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


# ── /weixin/callback ──────────────────────────────────────────────
@app.get("/weixin/callback")
async def weixin_verify(
    signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    """微信公众号服务器验证（GET）"""
    from weixin_oa import verify_signature
    if verify_signature(signature, timestamp, nonce):
        return Response(content=echostr, media_type="text/plain")
    raise HTTPException(403, "signature verification failed")


@app.post("/weixin/callback")
async def weixin_message(request: Request):
    """微信公众号消息回调（POST）— 异步处理，立即返回空响应"""
    xml_bytes = await request.body()
    if not xml_bytes:
        return Response(content="", media_type="text/plain")

    from weixin_oa import parse_xml_message, handle_message

    msg = parse_xml_message(xml_bytes)
    db_pool = None
    if _db_ok:
        db_pool = get_pool()

    reply = await handle_message(msg, db_pool)

    if reply:
        return Response(content=reply, media_type="text/xml")
    return Response(content="", media_type="text/plain")


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
    """个性化批量推送（Phase 2 更新）

    支持两种调用方式：
    1. 传 briefing_id → 推送指定简报
    2. 传 type（morning/evening）→ 取最新简报推送
    """
    # 获取简报
    briefing = None

    if req.briefing_id:
        try:
            UUID(req.briefing_id)
        except ValueError:
            raise HTTPException(400, "invalid briefing id format")

        try:
            pool = _db()
            briefing_row = await pool.fetchrow(
                "SELECT id, type, date, tl_dr, sections FROM briefings WHERE id=$1",
                UUID(req.briefing_id),
            )
            if not briefing_row:
                raise HTTPException(404, "briefing not found")
            briefing = {
                "id": str(briefing_row["id"]),
                "type": briefing_row["type"],
                "date": str(briefing_row["date"]),
                "tl_dr": briefing_row["tl_dr"],
                "sections": briefing_row["sections"],
            }
        except RuntimeError:
            briefing = next((b for b in get_briefings() if b["id"] == req.briefing_id), None)
            if not briefing:
                raise HTTPException(404, "briefing not found")

    elif req.type:
        if req.type not in ("morning", "evening"):
            raise HTTPException(400, "type must be morning or evening")
        # 按 type 取最新简报
        try:
            pool = _db()
            briefing_row = await pool.fetchrow(
                "SELECT id, type, date, tl_dr, sections FROM briefings WHERE type=$1 ORDER BY date DESC LIMIT 1",
                req.type,
            )
            if not briefing_row:
                raise HTTPException(404, "no briefing found")
            briefing = {
                "id": str(briefing_row["id"]),
                "type": briefing_row["type"],
                "date": str(briefing_row["date"]),
                "tl_dr": briefing_row["tl_dr"],
                "sections": briefing_row["sections"],
            }
        except RuntimeError:
            for b in get_briefings():
                if b["type"] == req.type:
                    briefing = b
                    break
            if not briefing:
                raise HTTPException(404, "no briefing found")
    else:
        raise HTTPException(400, "must provide briefing_id or type")

    # 获取订阅者（含标签偏好）
    try:
        pool = _db()
        subscribers = await pool.fetch(
            "SELECT openid, morning_enabled, evening_enabled, preferences FROM subscriptions WHERE subscribed=true"
        )
        targets = []
        for s in subscribers:
            prefs = s["preferences"]
            if isinstance(prefs, str):
                prefs = json.loads(prefs)
            user_tags = prefs.get("tags", []) if isinstance(prefs, dict) else []
            targets.append({
                "openid": s["openid"],
                "morning_enabled": s["morning_enabled"],
                "evening_enabled": s["evening_enabled"],
                "tags": user_tags,
            })
    except RuntimeError:
        targets = get_subscriptions()
        for t in targets:
            if "tags" not in t:
                t["tags"] = []

    # 按简报类型过滤订阅者
    btype = briefing["type"]
    targets = [
        t for t in targets
        if (btype == "morning" and t.get("morning_enabled", True))
        or (btype == "evening" and t.get("evening_enabled", True))
    ]

    if not os.getenv("WECHAT_APPID"):
        return {
            "status": "dry_run",
            "briefing_id": str(briefing["id"]),
            "total": len(targets),
            "success": 0,
            "failed": 0,
            "personalized": 0,
            "default_fallback": len(targets),
            "detail": [{"openid": t["openid"], "result": "dry_run"} for t in targets],
        }

    from push import batch_push
    result = await batch_push(briefing, targets)
    return result
