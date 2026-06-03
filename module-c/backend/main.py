"""Module C — 微信小程序+公众号后端 (:8003)

Phase 2 更新：新增公众号回调、标签管理、用户行为追踪、个性化推送。
Phase 3 更新：新增 Agent 自主扩展信源 API（信源健康度 / 推荐列表 / 审核）。
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

# Phase 3: 引入 source_agent（module-a），用于信源健康度 API
_source_agent = None
try:
    import importlib.util

    _agent_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "module-a",
        "source_agent.py",
    )
    if os.path.exists(_agent_path):
        _spec = importlib.util.spec_from_file_location("source_agent", _agent_path)
        _source_agent = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_source_agent)
except Exception:
    _source_agent = None

app = FastAPI(title="Module C - WeChat Mini Program + OA Backend")

# 数据库是否可用
_db_ok = False

# 注册 Phase 2 路由模块
from tags import router as tags_router, set_db_pool as set_tags_db_pool
app.include_router(tags_router)

# 注册 Phase 3 趋势路由
from trends import router as trends_router, set_db_pool as set_trends_db_pool
app.include_router(trends_router)


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
        set_trends_db_pool(pool)
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
        raw_stats = row["raw_stats"] or {}
        if isinstance(raw_stats, str):
            raw_stats = json.loads(raw_stats)
        return {
            "id": str(row["id"]),
            "type": row["type"],
            "date": str(row["date"]),
            "headline": raw_stats.get("headline", {}),
            "tl_dr": row["tl_dr"],
            "sections": row["sections"],
            "key_takeaways": row["key_takeaways"],
            "raw_stats": raw_stats,
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


# ══════════════════════════════════════════════════════════════════
# Phase 3: Agent 信源健康度 API
# ══════════════════════════════════════════════════════════════════


@app.get("/api/sources/health")
async def get_sources_health():
    """返回各标签覆盖率（绿/黄/红三档）"""
    try:
        pool = _db()
    except RuntimeError:
        return _mock_sources_health()

    if _source_agent is not None:
        return {"items": await _source_agent.get_sources_health(pool)}

    # 回退：直接 SQL 查询
    from datetime import date, timedelta

    cutoff = date.today() - timedelta(days=3)
    tags = await pool.fetch(
        "SELECT tag, label_zh FROM tag_catalog ORDER BY sort_order"
    )
    items = []
    for row in tags:
        tag = row["tag"]
        count = await pool.fetchval(
            """SELECT COUNT(*) FROM raw_items
               WHERE fetched_at >= $1 AND metadata->'tags' ? $2""",
            cutoff,
            tag,
        )
        if count >= 5:
            health = "green"
        elif count >= 2:
            health = "yellow"
        else:
            health = "red"

        pending = await pool.fetchval(
            "SELECT COUNT(*) FROM recommended_sources WHERE tag=$1 AND status='pending'",
            tag,
        )

        items.append(
            {
                "tag": tag,
                "label_zh": row["label_zh"] or tag,
                "count": count,
                "health": health,
                "coverage_threshold": 2,
                "coverage_days": 3,
                "recommendations_pending": pending or 0,
            }
        )
    return {"items": items}


def _mock_sources_health():
    """无 DB 时的 mock 信源健康度"""
    mock_tags = [
        {"tag": "LLM", "label_zh": "大模型", "count": 12, "health": "green"},
        {"tag": "开源", "label_zh": "开源项目", "count": 8, "health": "green"},
        {"tag": "Agent", "label_zh": "智能体", "count": 6, "health": "green"},
        {"tag": "基础设施", "label_zh": "基础设施", "count": 4, "health": "yellow"},
        {"tag": "RAG", "label_zh": "RAG", "count": 1, "health": "red"},
        {"tag": "多模态", "label_zh": "多模态", "count": 5, "health": "green"},
        {"tag": "AI编程", "label_zh": "AI编程", "count": 7, "health": "green"},
        {"tag": "AI产品", "label_zh": "AI产品", "count": 3, "health": "yellow"},
        {"tag": "AI安全", "label_zh": "AI安全", "count": 1, "health": "red"},
        {"tag": "AI政策", "label_zh": "AI政策", "count": 2, "health": "yellow"},
        {"tag": "融资", "label_zh": "融资并购", "count": 5, "health": "green"},
        {"tag": "Python", "label_zh": "Python", "count": 9, "health": "green"},
        {"tag": "科技", "label_zh": "科技", "count": 10, "health": "green"},
        {"tag": "体育", "label_zh": "体育", "count": 6, "health": "green"},
        {"tag": "时事", "label_zh": "时事", "count": 8, "health": "green"},
    ]
    for t in mock_tags:
        t.setdefault("coverage_threshold", 2)
        t.setdefault("coverage_days", 3)
        t.setdefault("recommendations_pending", 0)
    # 给红色标签加 mock pending
    for t in mock_tags:
        if t["health"] == "red":
            t["recommendations_pending"] = 2 if t["tag"] == "RAG" else 1
    return {"items": mock_tags}


@app.get("/api/sources/recommendations")
async def get_sources_recommendations(
    status: str = Query("pending", description="pending | approved | rejected"),
):
    """返回待审/已处理推荐信源列表"""
    try:
        pool = _db()
    except RuntimeError:
        return {"items": _mock_recommendations(status)}

    if _source_agent is not None:
        items = await _source_agent.get_recommendations(pool, status)
        return {"items": items}

    # 回退：直接 SQL 查询
    rows = await pool.fetch(
        """SELECT r.*, tc.label_zh AS tag_label
           FROM recommended_sources r
           LEFT JOIN tag_catalog tc ON r.tag = tc.tag
           WHERE r.status = $1
           ORDER BY r.quality_score DESC, r.discovered_at DESC""",
        status,
    )
    items = []
    for r in rows:
        items.append(
            {
                "id": str(r["id"]),
                "tag": r["tag"],
                "tag_label": r["tag_label"],
                "name": r["name"],
                "url": r["url"],
                "rss_url": r["rss_url"],
                "quality_score": float(r["quality_score"]) if r["quality_score"] else None,
                "relevance_score": float(r["relevance_score"]) if r["relevance_score"] else None,
                "freshness_score": float(r["freshness_score"]) if r["freshness_score"] else None,
                "authority_score": float(r["authority_score"]) if r["authority_score"] else None,
                "status": r["status"],
                "discovered_at": r["discovered_at"].isoformat() if r["discovered_at"] else None,
                "approved_at": r["approved_at"].isoformat() if r["approved_at"] else None,
            }
        )
    return {"items": items}


def _mock_recommendations(status: str) -> list[dict]:
    """无 DB 时的 mock 推荐数据"""
    if status != "pending":
        return []
    return [
        {
            "id": "mock-rec-001",
            "tag": "RAG",
            "tag_label": "RAG",
            "name": "LlamaIndex Blog",
            "url": "https://blog.llamaindex.ai",
            "rss_url": "https://blog.llamaindex.ai/feed",
            "quality_score": 4.3,
            "relevance_score": 5,
            "freshness_score": 4,
            "authority_score": 4,
            "status": "pending",
            "discovered_at": "2026-06-03T10:00:00+08:00",
            "approved_at": None,
        },
        {
            "id": "mock-rec-002",
            "tag": "RAG",
            "tag_label": "RAG",
            "name": "RAG Research Papers (Arxiv)",
            "url": "https://arxiv.org/list/cs.IR/recent",
            "rss_url": "https://rss.arxiv.org/rss/cs.IR",
            "quality_score": 3.8,
            "relevance_score": 4,
            "freshness_score": 5,
            "authority_score": 3,
            "status": "pending",
            "discovered_at": "2026-06-03T10:00:00+08:00",
            "approved_at": None,
        },
        {
            "id": "mock-rec-003",
            "tag": "AI安全",
            "tag_label": "AI安全",
            "name": "AI Safety Blog (Anthropic)",
            "url": "https://www.anthropic.com/research",
            "rss_url": None,
            "quality_score": 4.5,
            "relevance_score": 5,
            "freshness_score": 4,
            "authority_score": 5,
            "status": "pending",
            "discovered_at": "2026-06-03T10:00:00+08:00",
            "approved_at": None,
        },
    ]


@app.post("/api/sources/approve")
async def approve_source(source_id: str = Query(..., description="推荐信源 ID")):
    """管理员通过推荐信源（将 status 改为 approved）"""
    try:
        UUID(source_id)
    except ValueError:
        raise HTTPException(400, "invalid source id format")

    try:
        pool = _db()
    except RuntimeError:
        # Mock 模式：返回模拟结果
        return {
            "status": "ok",
            "source_id": source_id,
            "message": "信源已通过（mock 模式）",
        }

    if _source_agent is not None:
        result = await _source_agent.approve_source(pool, source_id)
        if result is None:
            raise HTTPException(404, "source not found or already processed")
        return {"status": "ok", "source": result}

    # 回退：直接 SQL
    row = await pool.fetchrow(
        """UPDATE recommended_sources
           SET status = 'approved', approved_at = now()
           WHERE id = $1 AND status = 'pending'
           RETURNING *""",
        UUID(source_id),
    )
    if row is None:
        raise HTTPException(404, "source not found or already processed")

    return {
        "status": "ok",
        "source": {
            "id": str(row["id"]),
            "tag": row["tag"],
            "name": row["name"],
            "url": row["url"],
            "rss_url": row["rss_url"],
            "quality_score": float(row["quality_score"]) if row["quality_score"] else None,
            "status": row["status"],
            "approved_at": row["approved_at"].isoformat() if row["approved_at"] else None,
        },
    }
