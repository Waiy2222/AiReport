"""Module C — 微信小程序+公众号后端 (:8003)

Phase 2 更新：新增公众号回调、标签管理、用户行为追踪、个性化推送。
Phase 3 更新：新增 Agent 自主扩展信源 API（信源健康度 / 推荐列表 / 审核）。
无 PostgreSQL 时自动使用内置假数据，无需任何外部依赖即可运行。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# 加载 .env（与其他模块一致）
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

import json
import asyncio
import httpx
from datetime import datetime, timezone
import uuid
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles

from db import get_pool, init_db, close_db, migrate_personalized_briefings
from models import SubscribeRequest, UnsubscribeRequest, WechatLoginRequest, PushRequest
from models import GenerateRequest, GenerateResponse, TaskStatusResponse
from models import MyBriefingsResponse, MyBriefingItem
from models import (
    VideoGenerateRequest, VideoGenerateResponse,
    VideoStatusResponse, VideoListResponse,
)
from mock_data import get_briefings, get_subscriptions
from video_proxy import (
    VIDEO_SERVICE_URL, generate_video, get_video_status,
    list_videos, get_video_meta,
)

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

# ── 个性化简报：任务存储 ────────────────────────────────
# 内存任务存储：task_id → {status, briefing_id, error, created_at}
_task_store: dict[str, dict] = {}
# 用户级任务锁：openid → task_id（同一用户只能有一个进行中任务）
_user_tasks: dict[str, str] = {}
# 全局并发锁：防止过多同时抓取打满连接池（最多2个并行）
_gen_semaphore = asyncio.Semaphore(2)
# 个性化简报通过 HTTP 调用 module-b:/run-personalized（不再 importlib 加载）
B_PERSONALIZED_URL = os.getenv("B_PERSONALIZED_URL", "http://localhost:8002/run-personalized")

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
        await migrate_personalized_briefings(pool)
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


def _parse_json_field(val):
    """解析数据库中的 JSON 字段：字符串→解析，已是 list/dict 直接返回"""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


def _normalize_sections(sections):
    """兼容旧数据：section_title -> tag + title"""
    if isinstance(sections, str):
        sections = json.loads(sections)
    for s in sections:
        if "tag" not in s or not s.get("tag"):
            s["tag"] = s.get("section_title", "综合")
        if "title" not in s or not s.get("title"):
            s["title"] = s.get("section_title", "综合")
    return sections


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


# ── /api/wechat/login ────────────────────────────────────────────
@app.post("/api/wechat/login")
async def wechat_login(req: WechatLoginRequest):
    """小程序登录：wx.login() 的 code 换取 openid"""
    import hashlib
    from config import settings
    from auth import code_to_openid

    # 开发环境未配置 AppID/Secret 时，返回稳定 mock openid，保证本地可跑通
    if not settings.WX_APPID or not settings.WX_SECRET:
        mock = "dev_" + hashlib.md5(req.js_code.encode("utf-8")).hexdigest()[:16]
        return {"openid": mock, "mock": True}

    openid = await code_to_openid(req.js_code)
    if not openid:
        raise HTTPException(401, "微信登录失败：code 无效或已过期")
    return {"openid": openid, "mock": False}


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
            "tl_dr": _parse_json_field(row["tl_dr"]),
            "sections": _normalize_sections(row["sections"]),
            "key_takeaways": _parse_json_field(row["key_takeaways"]),
            "raw_stats": raw_stats,
            "generated_at": row["generated_at"].isoformat(),
        }
    except RuntimeError:
        all_briefings = get_briefings()
        for b in all_briefings:
            if b["type"] == type:
                b["sections"] = _normalize_sections(b.get("sections", []))
                return b
        raise HTTPException(404, "no briefing found")


# ── /api/briefings/history ───────────────────────────────────────
@app.get("/api/briefings/history")
async def get_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="搜索关键词"),
    type: str = Query("", description="筛选类型: morning / evening / 空=全部"),
    date_from: str = Query("", description="起始日期 YYYY-MM-DD"),
    date_to: str = Query("", description="结束日期 YYYY-MM-DD"),
    tag: str = Query("", description="标签筛选，如 LLM, Agent"),
):
    try:
        pool = _db()

        # 动态构建 WHERE 条件（tag 在 Python 侧过滤，避免 JSONB 兼容问题）
        conditions: list[str] = []
        params: list = []
        param_idx = 0

        def next_param(val):
            nonlocal param_idx
            param_idx += 1
            params.append(val)
            return f"${param_idx}"

        if keyword:
            conditions.append(f"tl_dr::text ILIKE {next_param(f'%{keyword}%')}")
        if type:
            conditions.append(f"type = {next_param(type)}")
        if date_from:
            conditions.append(f"date >= {next_param(date_from)}::date")
        if date_to:
            conditions.append(f"date <= {next_param(date_to)}::date")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # 无 tag 筛选：直接分页查询
        if not tag:
            offset = (page - 1) * size
            query = f"""SELECT id, type, date, tl_dr, sections, generated_at, is_personalized, interest_text, interest_tags FROM briefings
                         {where_clause}
                         ORDER BY date DESC OFFSET {next_param(offset)} LIMIT {next_param(size)}"""
            rows = await pool.fetch(query, *params)
            count_params = params[:-2] if (len(params) >= 2) else params
            count_query = f"SELECT COUNT(*) FROM briefings {where_clause}"
            total = await pool.fetchval(count_query, *count_params)
        else:
            # tag 筛选：全量查出再 Python 侧过滤（避免 JSONB 运算符 asyncpg 兼容问题）
            query = f"""SELECT id, type, date, tl_dr, sections, generated_at, is_personalized, interest_text, interest_tags FROM briefings
                         {where_clause}
                         ORDER BY date DESC"""
            all_rows = await pool.fetch(query, *params)
            print(f"[history] tag filter: tag={tag}, before_filter={len(all_rows)}")

            # 诊断：打印前2条简报的 item tags 样本
            for idx, r in enumerate(all_rows[:2]):
                sections = r["sections"]
                if isinstance(sections, str):
                    sections = json.loads(sections)
                sample_tags = []
                for s in (sections or [])[:2]:
                    for item in (s.get("items") or [])[:1]:
                        sample_tags.append(item.get("tags", []))
                print(f"[history] sample[{idx}]: date={r['date']}, item_tags={sample_tags}")

            def _has_item_tag(row):
                sections = row["sections"]
                if isinstance(sections, str):
                    sections = json.loads(sections)
                for s in (sections or []):
                    for item in (s.get("items") or []):
                        if tag in (item.get("tags") or []):
                            return True
                return False

            filtered = [r for r in all_rows if _has_item_tag(r)]
            total = len(filtered)
            offset = (page - 1) * size
            rows = filtered[offset:offset + size]
            print(f"[history] tag filter: after_filter={total}, page_rows={len(rows)}")

        items = [
            {
                "id": str(r["id"]),
                "type": r["type"],
                "date": str(r["date"]),
                "tl_dr": _parse_json_field(r["tl_dr"]),
                "sections": _normalize_sections(r["sections"]),
                "generated_at": r["generated_at"].isoformat(),
                "is_personalized": r.get("is_personalized", False),
                "interest_text": r.get("interest_text", ""),
                "interest_tags": _parse_json_field(r.get("interest_tags")),
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
        if type:
            all_briefings = [b for b in all_briefings if b["type"] == type]
        if date_from:
            all_briefings = [b for b in all_briefings if b["date"] >= date_from]
        if date_to:
            all_briefings = [b for b in all_briefings if b["date"] <= date_to]
        if tag:
            def _has_item_tag(briefing):
                for s in (briefing.get("sections") or []):
                    for item in (s.get("items") or []):
                        if tag in (item.get("tags") or []):
                            return True
                return False
            all_briefings = [b for b in all_briefings if _has_item_tag(b)]
        total = len(all_briefings)
        start = (page - 1) * size
        end = start + size
        items = [
            {
                "id": b["id"],
                "type": b["type"],
                "date": b["date"],
                "tl_dr": b["tl_dr"],
                "sections": _normalize_sections(b.get("sections", [])),
                "generated_at": b["generated_at"],
            }
            for b in all_briefings[start:end]
        ]

    return {"page": page, "size": size, "total": total, "items": items}


# ── /api/briefings/my（必须在 {briefing_id} 之前，否则 "my" 被 UUID 劫持）──
@app.get("/api/briefings/my", response_model=MyBriefingsResponse)
async def get_my_briefings(
    openid: str = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """获取用户的专属简报历史"""
    try:
        pool = _db()
        offset = (page - 1) * size

        total = await pool.fetchval(
            "SELECT COUNT(*) FROM briefings WHERE requested_by = $1 AND is_personalized = true",
            openid,
        )

        rows = await pool.fetch(
            """SELECT id, type, date, interest_text, interest_tags, sections, generated_at
               FROM briefings
               WHERE requested_by = $1 AND is_personalized = true
               ORDER BY date DESC, generated_at DESC
               OFFSET $2 LIMIT $3""",
            openid, offset, size,
        )

        items = [
            MyBriefingItem(
                id=str(r["id"]),
                type=r["type"],
                date=str(r["date"]),
                interest_text=r["interest_text"],
                interest_tags=_parse_json_field(r["interest_tags"]),
                sections=_normalize_sections(r["sections"]),
                generated_at=r["generated_at"].isoformat(),
            )
            for r in rows
        ]

        return MyBriefingsResponse(page=page, size=size, total=total or 0, items=items)
    except RuntimeError:
        return MyBriefingsResponse(page=page, size=size, total=0, items=[])


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
            "tl_dr": _parse_json_field(row["tl_dr"]),
            "sections": _normalize_sections(row["sections"]),
            "key_takeaways": _parse_json_field(row["key_takeaways"]),
            "raw_stats": row["raw_stats"],
            "generated_at": row["generated_at"].isoformat(),
            "is_personalized": row["is_personalized"],
            "interest_text": row["interest_text"] or "",
            "interest_tags": _parse_json_field(row["interest_tags"]),
        }
    except RuntimeError:
        for b in get_briefings():
            if b["id"] == briefing_id:
                b["sections"] = _normalize_sections(b.get("sections", []))
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
                "tl_dr": _parse_json_field(briefing_row["tl_dr"]),
                "sections": _parse_json_field(briefing_row["sections"]),
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
                "tl_dr": _parse_json_field(briefing_row["tl_dr"]),
                "sections": _parse_json_field(briefing_row["sections"]),
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


# ══════════════════════════════════════════════════════════════════
# 个性化简报 API
# ══════════════════════════════════════════════════════════════════


def _load_interest_parser():
    """延迟加载 interest_parser 模块"""
    import importlib.util
    _ip_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "module-b", "ai", "interest_parser.py",
    )
    if not os.path.exists(_ip_path):
        raise RuntimeError("interest_parser module not found")
    _ip_spec = importlib.util.spec_from_file_location("interest_parser", _ip_path)
    _ip_mod = importlib.util.module_from_spec(_ip_spec)
    _ip_spec.loader.exec_module(_ip_mod)
    return _ip_mod


async def _run_personalized_generation(
    task_id: str,
    pool,
    briefing_type: str,
    briefing_date: str,
    filter_tags: list[str],
    openid: str,
    interest_text: str,
    interest_tags: list[str],
    search_keywords: list[str] | None = None,
):
    """后台执行个性化简报生成，完成后更新 _task_store"""
    # 全局并发控制：超过2个任务排队等待，防止打满连接池
    async with _gen_semaphore:
        await _do_generate(task_id, pool, briefing_type, briefing_date,
                           filter_tags, openid, interest_text, interest_tags, search_keywords)


async def _do_generate(
    task_id: str, pool, briefing_type: str, briefing_date: str,
    filter_tags: list[str], openid: str, interest_text: str,
    interest_tags: list[str], search_keywords: list[str] | None = None,
):
    """实际执行生成逻辑（由 _run_personalized_generation 在信号量内调用）"""
    try:
        # ① 外部抓取：两级重试，确保有数据
        #    第一级 → 关键词搜索（快，精准）
        #    第二级 → 全量抓取 RSS + 关键词（慢，全面）
        #    第三级 → 才 fallback 到 DB 旧数据（兜底）
        A_URL = os.getenv("A_URL", "http://localhost:8001/run")
        search_kws = list(set(search_keywords or []))
        if not search_kws:
            search_kws = list(set(filter_tags + interest_tags))

        scraped_batch_id = None
        scrape_level = 0
        SCRAPE_LEVELS = [
            # (level_label, search_only, hours_back, timeout)
            ("L1_keyword",  True,  48, 30),   # 关键词搜索（快，精准）
            # 个性化简报不做 L2 全量 RSS（RSS 是科技源，对用户兴趣无效，且耗时 60s+）
        ]

        if search_kws:
            for level_label, search_only, hours_back, timeout in SCRAPE_LEVELS:
                scrape_level += 1
                batch_id = str(uuid.uuid4())
                try:
                    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as http_client:
                        r = await http_client.post(A_URL, json={
                            "batch_id": batch_id,
                            "hours_back": hours_back,
                            "search_keywords": search_kws,
                            "search_only": search_only,
                        })
                        if r.status_code == 200:
                            result = r.json()
                            fetched = result.get("fetched", 0)
                            per_source = result.get("per_source", {})
                            gnews = per_source.get("google_news_search", 0)
                            rss_count = sum(
                                v for k, v in per_source.items()
                                if k != "google_news_search"
                            )
                            print(f"[personalized] {level_label} scrape: {fetched} items "
                                  f"(gnews={gnews}, rss={rss_count}, keywords={search_kws[:3]})")
                            if fetched > 0:
                                scraped_batch_id = batch_id
                                break  # 有数据就停，不继续下一级
                            else:
                                print(f"[personalized] {level_label} returned 0 items, "
                                      f"escalating to next level...")
                        else:
                            print(f"[personalized] {level_label} HTTP {r.status_code}: "
                                  f"{r.text[:200]}")
                except Exception as e:
                    print(f"[personalized] {level_label} error: {e}")

        # ② 读抓取数据：优先刚才的 scraped_batch_id，否则 fallback 到 DB 最新 batch
        async with pool.acquire() as conn:
            rows = None
            if scraped_batch_id:
                rows = await conn.fetch(
                    "SELECT id, source, title, url, content, author, published_at, metadata, batch_id "
                    "FROM raw_items WHERE batch_id = $1",
                    scraped_batch_id,
                )
                if rows:
                    print(f"[personalized] Using scraped batch {scraped_batch_id}: "
                          f"{len(rows)} items (level={scrape_level})")

            if not rows:
                print("[personalized] No scraped data, falling back to latest DB batch")
                latest_batch = await conn.fetchval(
                    "SELECT batch_id FROM raw_items ORDER BY fetched_at DESC LIMIT 1"
                )
                if not latest_batch:
                    _task_store[task_id]["status"] = "failed"
                    _task_store[task_id]["error"] = "暂无新闻数据，请稍后再试"
                    return
                rows = await conn.fetch(
                    "SELECT id, source, title, url, content, author, published_at, metadata, batch_id "
                    "FROM raw_items WHERE batch_id = $1",
                    latest_batch,
                )

        items = [dict(r) for r in rows]

        if not items:
            _task_store[task_id]["status"] = "failed"
            _task_store[task_id]["error"] = "暂无新闻数据，请稍后再试"
            return

        # 同步 metadata 中的 tags 和 ai_score 到 item 顶层
        for it in items:
            meta = it.get("metadata")
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            if not isinstance(meta, dict):
                meta = {}
            if not it.get("tags") and meta.get("tags"):
                it["tags"] = meta["tags"]
            if not it.get("ai_score") and meta.get("ai_score"):
                it["ai_score"] = float(meta["ai_score"])
            it["metadata"] = meta

        # ③ 调用 module-b 轻量流水线（HTTP，解耦）
        payload = {
            "type": briefing_type,
            "date": briefing_date,
            "batch_id": scraped_batch_id or "fallback",
            "tags": filter_tags,
            "openid": openid,
            "interest_text": interest_text,
            "interest_tags": interest_tags,
            "search_keywords": search_keywords,
            "items": items,
        }
        try:
            # 手动序列化以处理 datetime 对象（asyncpg 返回的 rows 包含 datetime）
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            async with httpx.AsyncClient(timeout=300, trust_env=False) as http_client:
                r = await http_client.post(
                    B_PERSONALIZED_URL,
                    content=body,
                    headers={"Content-Type": "application/json"},
                )
                if r.status_code != 200:
                    raise Exception(f"module-b returned {r.status_code}: {r.text[:300]}")
                result = r.json()
        except Exception as e:
            raise Exception(f"调用 module-b 个性化流水线失败: {e}")

        _task_store[task_id]["status"] = "completed"
        _task_store[task_id]["briefing_id"] = str(result["briefing_id"])

    except Exception as e:
        import traceback
        traceback.print_exc()
        _task_store[task_id]["status"] = "failed"
        _task_store[task_id]["error"] = str(e)[:200]


@app.post("/api/briefings/generate", response_model=GenerateResponse)
async def generate_briefing(req: GenerateRequest):
    """触发个性化简报生成（通过 HTTP 调用 module-b:/run-personalized）"""
    # 检查数据库可用
    try:
        _db()
    except RuntimeError:
        raise HTTPException(503, "database not available")

    # ① 输入校验：敏感词 + 新闻相关性
    try:
        _ip = _load_interest_parser()
        validation = await _ip.validate_input(req.interest_text)
        if not validation["valid"]:
            return GenerateResponse(
                task_id="",
                status="rejected",
                valid=False,
                error=validation["error"],
            )
    except Exception as e:
        # 校验模块加载失败不阻塞用户，跳过校验
        print(f"[generate] interest_parser unavailable, skipping validation: {e}")

    # ② LLM 兴趣解析 + 关键词拆解
    all_tags = list(req.tags)
    search_keywords: list[str] = list(req.tags)

    # 从原始输入直接拆解关键词（逗号/空格/顿号分隔），不依赖 LLM
    import re as _re
    raw_terms = [t.strip() for t in _re.split(r'[，,、\s]+', req.interest_text) if t.strip()]
    raw_terms = [t for t in raw_terms if len(t) >= 2 and not t.isdigit()]

    try:
        _ip = _load_interest_parser()
        parsed = await _ip.parse_interests(req.interest_text)
        all_tags = list(set(parsed.get("tags", []) + req.tags))
        search_keywords = list(set(parsed.get("keywords", []) + req.tags + raw_terms))
        if not search_keywords:
            search_keywords = all_tags + raw_terms
    except Exception as e:
        print(f"[generate] interest parsing failed: {e}")
        all_tags = list(req.tags)
        search_keywords = list(set(req.tags + raw_terms))

    # 兜底：all_tags 为空但 search_keywords 不为空，从关键词中取前5个作为标签
    if not all_tags and search_keywords:
        all_tags = search_keywords[:5]
        print(f"[generate] LLM returned no tags, using search_keywords as tags: {all_tags}")

    if not all_tags and not search_keywords:
        return GenerateResponse(
            task_id="",
            status="rejected",
            valid=False,
            error="请输入你感兴趣的新闻关键词，如：AI、自动驾驶、电子竞技",
        )

    # ③ 用户级并发控制：取消旧任务
    task_id = str(uuid.uuid4())
    old_task_id = _user_tasks.get(req.openid)
    if old_task_id and old_task_id in _task_store:
        if _task_store[old_task_id].get("status") == "processing":
            _task_store[old_task_id]["status"] = "cancelled"
            _task_store[old_task_id]["error"] = "Replaced by newer request"
    _user_tasks[req.openid] = task_id

    # ④ 存入任务记录
    _task_store[task_id] = {
        "status": "processing",
        "briefing_id": None,
        "error": None,
        "created_at": datetime.now(timezone.utc),
    }

    # ⑤ 启动后台生成任务
    pool = _db()
    briefing_date = datetime.now().strftime("%Y-%m-%d")

    asyncio.create_task(
        _run_personalized_generation(
            task_id=task_id,
            pool=pool,
            briefing_type=req.type,
            briefing_date=briefing_date,
            filter_tags=all_tags,
            openid=req.openid,
            interest_text=req.interest_text,
            interest_tags=search_keywords if search_keywords else all_tags,
            search_keywords=search_keywords,
        )
    )

    return GenerateResponse(task_id=task_id, status="processing", valid=True)


@app.get("/api/briefings/generate/{task_id}", response_model=TaskStatusResponse)
async def get_generation_status(task_id: str):
    """轮询个性化简报生成状态"""
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        briefing_id=task.get("briefing_id"),
        error=task.get("error"),
    )


@app.get("/api/briefings/my/latest")
async def get_my_latest_briefing(
    openid: str = Query(...),
    type: str = Query("morning", description="morning or evening"),
):
    """获取用户最新的专属简报（用于首页「我的报道」）"""
    try:
        pool = _db()
        row = await pool.fetchrow(
            """SELECT id, type, date, tl_dr, sections, key_takeaways, raw_stats,
                      interest_text, interest_tags, generated_at
               FROM briefings
               WHERE requested_by = $1 AND is_personalized = true AND type = $2
               ORDER BY date DESC, generated_at DESC
               LIMIT 1""",
            openid, type,
        )
        if not row:
            raise HTTPException(404, "no personalized briefing found")

        raw_stats = row["raw_stats"] or {}
        if isinstance(raw_stats, str):
            raw_stats = json.loads(raw_stats)

        return {
            "id": str(row["id"]),
            "type": row["type"],
            "date": str(row["date"]),
            "headline": raw_stats.get("headline", {}),
            "tl_dr": _parse_json_field(row["tl_dr"]),
            "sections": _normalize_sections(row["sections"]),
            "key_takeaways": _parse_json_field(row["key_takeaways"]),
            "interest_text": row["interest_text"],
            "interest_tags": _parse_json_field(row["interest_tags"]),
            "generated_at": row["generated_at"].isoformat(),
        }
    except RuntimeError:
        raise HTTPException(503, "database not available")


# ══════════════════════════════════════════════════════════════════
# 视频生成 API（代理 Module-F :8006）
# ══════════════════════════════════════════════════════════════════

import traceback as _tb


@app.post("/api/videos/generate", response_model=VideoGenerateResponse)
async def video_generate(req: VideoGenerateRequest):
    """触发视频生成（代理 Module-F /generate）"""
    try:
        result = await generate_video(req.keyword)
        return VideoGenerateResponse(
            video_id=result.get("video_id", ""),
            status=result.get("status", "processing"),
            message=result.get("message", "视频生成已启动"),
        )
    except httpx.ConnectError:
        raise HTTPException(503, f"视频生成服务不可用 ({VIDEO_SERVICE_URL})")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"视频服务错误: {e.response.text[:200]}")
    except Exception as e:
        _tb.print_exc()
        raise HTTPException(500, f"视频生成失败: {str(e)[:200]}")


@app.get("/api/videos/status/{video_id}", response_model=VideoStatusResponse)
async def video_status(video_id: str):
    """轮询视频生成状态（代理 Module-F /status/{video_id}）"""
    try:
        result = await get_video_status(video_id)
        return VideoStatusResponse(
            video_id=result.get("video_id", video_id),
            status=result.get("status", "unknown"),
            title=result.get("title"),
            output_path=result.get("output_path"),
            cover_path=result.get("cover_path"),
            duration_seconds=result.get("duration_seconds"),
            error_msg=result.get("error_msg"),
        )
    except httpx.ConnectError:
        raise HTTPException(503, f"视频生成服务不可用 ({VIDEO_SERVICE_URL})")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(404, f"视频不存在: {video_id}")
        raise HTTPException(e.response.status_code, f"视频服务错误")


@app.get("/api/videos/list", response_model=VideoListResponse)
async def video_list(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=50)):
    """视频列表（代理 Module-F /videos）"""
    try:
        result = await list_videos(page, size)
        return VideoListResponse(**result)
    except httpx.ConnectError:
        raise HTTPException(503, f"视频生成服务不可用 ({VIDEO_SERVICE_URL})")
    except Exception as e:
        _tb.print_exc()
        return VideoListResponse(items=[], total=0, page=page, size=size)


@app.get("/api/videos/{video_id}/file")
async def video_file(video_id: str):
    """流式返回 mp4 视频文件"""
    from fastapi.responses import StreamingResponse
    from pathlib import Path as _Path

    try:
        meta = await get_video_meta(video_id)
        output_path = meta.get("output_path")
        if not output_path or not _Path(output_path).exists():
            raise HTTPException(404, "视频文件不存在，可能尚未生成完成")
        file_path = _Path(output_path)

        def file_iterator():
            chunk_size = 1024 * 1024  # 1MB chunks
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            file_iterator(),
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'inline; filename="{file_path.name}"',
                "Content-Length": str(file_path.stat().st_size),
            },
        )
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(503, f"视频生成服务不可用 ({VIDEO_SERVICE_URL})")
    except Exception as e:
        _tb.print_exc()
        raise HTTPException(500, f"获取视频文件失败: {str(e)[:200]}")


@app.get("/api/videos/{video_id}/cover")
async def video_cover(video_id: str):
    """返回视频封面图片"""
    from fastapi.responses import FileResponse
    from pathlib import Path as _Path

    try:
        meta = await get_video_meta(video_id)
        cover_path = meta.get("cover_path")
        if not cover_path or not _Path(cover_path).exists():
            raise HTTPException(404, "封面不存在")
        return FileResponse(cover_path, media_type="image/jpeg")
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(503, f"视频生成服务不可用 ({VIDEO_SERVICE_URL})")
    except Exception as e:
        _tb.print_exc()
        raise HTTPException(500, f"获取封面失败: {str(e)[:200]}")
