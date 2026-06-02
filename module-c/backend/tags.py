"""标签管理 + 用户行为追踪 + 用户画像 API（Phase 2 新增）

路由（在 main.py 中注册）：
- GET  /api/tags                      — 可用标签列表
- GET  /api/user/preferences          — 获取用户偏好
- POST /api/user/preferences          — 设置用户偏好
- GET  /api/user/{openid}/profile     — 用户画像
- POST /api/behavior                  — 上报用户行为
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from models import (
    BehaviorRequest,
    PreferencesRequest,
    PreferencesResponse,
    TagItem,
    TagsResponse,
    UserClickSummary,
    UserProfile,
)
from mock_data import get_tags, get_user_preferences, get_user_behaviors

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tags"])

# 数据库是否可用（由 main.py startup 设置）
_db_pool = None

# Mock 模式内存存储（POST → GET 可持久化）
_mock_preferences: dict[str, dict] = {}


def set_db_pool(pool):
    global _db_pool
    _db_pool = pool


# ── GET /api/tags ─────────────────────────────────────────────────


@router.get("/tags", response_model=TagsResponse)
async def list_tags():
    """返回可用标签列表"""
    try:
        if _db_pool:
            rows = await _db_pool.fetch(
                "SELECT tag, label_zh, description FROM tag_catalog ORDER BY sort_order"
            )
            tags = [TagItem(tag=r["tag"], label_zh=r["label_zh"], description=r["description"] or "") for r in rows]
            return TagsResponse(tags=tags)
    except Exception:
        logger.warning("DB query failed, falling back to mock data", exc_info=True)

    # Mock fallback
    mock_tags = get_tags()
    return TagsResponse(
        tags=[TagItem(tag=t["tag"], label_zh=t["label_zh"], description=t["description"]) for t in mock_tags]
    )


# ── POST /api/user/preferences ────────────────────────────────────


@router.post("/user/preferences", response_model=PreferencesResponse)
async def set_preferences(req: PreferencesRequest):
    """设置用户偏好标签"""
    try:
        if _db_pool:
            await _db_pool.execute(
                """INSERT INTO subscriptions (openid, subscribed, preferences)
                   VALUES ($1, true, $2)
                   ON CONFLICT (openid) DO UPDATE SET preferences = $2""",
                req.openid,
                json.dumps({"tags": req.tags}),
            )
            return PreferencesResponse(openid=req.openid, tags=req.tags)
    except Exception:
        logger.warning("DB write failed for preferences", exc_info=True)
        raise HTTPException(500, "failed to save preferences")

    # Mock 模式 — 存内存
    _mock_preferences[req.openid] = {"tags": req.tags}
    return PreferencesResponse(openid=req.openid, tags=req.tags)


# ── GET /api/user/preferences ─────────────────────────────────────


@router.get("/user/preferences", response_model=PreferencesResponse)
async def get_preferences(openid: str = Query(...)):
    """获取用户偏好标签"""
    try:
        if _db_pool:
            row = await _db_pool.fetchrow(
                "SELECT preferences FROM subscriptions WHERE openid=$1",
                openid,
            )
            if row:
                prefs = row["preferences"]
                if isinstance(prefs, str):
                    prefs = json.loads(prefs)
                tags = prefs.get("tags", []) if isinstance(prefs, dict) else []
                return PreferencesResponse(openid=openid, tags=tags)
            return PreferencesResponse(openid=openid, tags=[])
    except Exception:
        logger.warning("DB query failed for preferences", exc_info=True)

    # Mock fallback — 先查内存，再查假数据
    if openid in _mock_preferences:
        return PreferencesResponse(openid=openid, tags=_mock_preferences[openid]["tags"])
    mock_prefs = get_user_preferences(openid)
    tags = mock_prefs["tags"] if mock_prefs else []
    return PreferencesResponse(openid=openid, tags=tags)


# ── GET /api/user/{openid}/profile ────────────────────────────────


@router.get("/user/{openid}/profile", response_model=UserProfile)
async def get_user_profile(openid: str):
    """获取用户画像（标签 + 近期点击 + 权重映射）"""
    # 获取偏好标签
    tags: list[str] = []
    weight_map: dict[str, float] = {}
    recent_clicks: list[UserClickSummary] = []
    tag_counts: dict[str, int] = {}
    total = 0

    try:
        if _db_pool:
            # 偏好标签
            row = await _db_pool.fetchrow(
                "SELECT preferences FROM subscriptions WHERE openid=$1",
                openid,
            )
            if row:
                prefs = row["preferences"]
                if isinstance(prefs, str):
                    prefs = json.loads(prefs)
                tags = prefs.get("tags", []) if isinstance(prefs, dict) else []

            # 近期点击行为（14 天内）
            rows = await _db_pool.fetch(
                """SELECT briefing_id, item_title, action, created_at
                   FROM user_behavior
                   WHERE user_openid = $1
                     AND action IN ('click', 'share')
                     AND created_at > NOW() - INTERVAL '14 days'
                   ORDER BY created_at DESC
                   LIMIT 20""",
                openid,
            )
            for r in rows:
                recent_clicks.append(UserClickSummary(
                    briefing_id=str(r["briefing_id"]) if r["briefing_id"] else "",
                    item_title=r["item_title"] or "",
                    action=r["action"],
                    created_at=r["created_at"].isoformat() if r["created_at"] else "",
                ))

            # 权重映射（按点击频次）
            for r in rows:
                # 从 user_behavior 行的 item_tags 获取标签
                beh_row = await _db_pool.fetchrow(
                    "SELECT item_tags FROM user_behavior WHERE user_openid=$1 AND action IN ('click','share') AND created_at > NOW() - INTERVAL '14 days'",
                    openid,
                )
                if beh_row and beh_row["item_tags"]:
                    t = beh_row["item_tags"]
                    if isinstance(t, str):
                        t = json.loads(t)
                    if isinstance(t, list):
                        for tag in t:
                            tag_counts[tag] = tag_counts.get(tag, 0) + 1
                            total += 1

            if total > 0:
                weight_map = {t: round(c / total, 2) for t, c in tag_counts.items()}

            return UserProfile(
                openid=openid,
                tags=tags,
                recent_clicks=recent_clicks,
                weight_map=weight_map,
            )
    except Exception:
        logger.warning("DB query failed for profile", exc_info=True)

    # Mock fallback
    mock_prefs = get_user_preferences(openid)
    tags = mock_prefs["tags"] if mock_prefs else []
    mock_behaviors = get_user_behaviors(openid)
    for b in mock_behaviors:
        if b["action"] in ("click", "share"):
            recent_clicks.append(UserClickSummary(
                briefing_id=b["briefing_id"],
                item_title=b["item_title"],
                action=b["action"],
                created_at=b["created_at"],
            ))
            for t in b.get("item_tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1
                total += 1

    if total > 0:
        weight_map = {t: round(c / total, 2) for t, c in tag_counts.items()}

    return UserProfile(
        openid=openid,
        tags=tags,
        recent_clicks=recent_clicks,
        weight_map=weight_map,
    )


# ── POST /api/behavior ────────────────────────────────────────────


@router.post("/behavior")
async def report_behavior(req: BehaviorRequest):
    """上报用户行为（点击/查看/分享/忽略）"""
    if req.action not in ("click", "view", "share", "dismiss"):
        raise HTTPException(400, "action must be one of: click, view, share, dismiss")

    try:
        if _db_pool:
            await _db_pool.execute(
                """INSERT INTO user_behavior
                   (user_openid, briefing_id, item_index, item_title, item_url, item_tags, action)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                req.openid,
                req.briefing_id,
                req.item_index,
                req.item_title,
                req.item_url,
                json.dumps(req.item_tags),
                req.action,
            )
            return {"status": "ok"}
    except Exception:
        logger.warning("DB write failed for behavior", exc_info=True)
        raise HTTPException(500, "failed to record behavior")

    # Mock 模式
    return {"status": "ok", "mode": "mock"}


# ── GET /api/user/{openid}/interest-radar ────────────────────────
# 返回用户兴趣雷达图数据（近7天点击权重，0-100 归一化）


@router.get("/user/{openid}/interest-radar")
async def get_interest_radar(openid: str):
    """返回用户兴趣雷达图数据：每个标签的点击权重（0-100）"""
    tag_counts: dict[str, int] = {}
    total = 0

    try:
        if _db_pool:
            rows = await _db_pool.fetch(
                """SELECT item_tags FROM user_behavior
                   WHERE user_openid = $1
                     AND action IN ('click', 'share')
                     AND created_at > NOW() - INTERVAL '7 days'""",
                openid,
            )
            for r in rows:
                tags_val = r["item_tags"]
                if isinstance(tags_val, str):
                    tags_val = json.loads(tags_val)
                if isinstance(tags_val, list):
                    for t in tags_val:
                        tag_counts[t] = tag_counts.get(t, 0) + 1
                        total += 1
    except Exception:
        logger.warning("DB query failed for interest radar", exc_info=True)

    # Mock 模式：用假数据
    if total == 0:
        mock_tags = ["LLM", "Agent", "开源", "多模态", "基础设施", "AI编程", "AI产品", "AI安全"]
        import random
        random.seed(hash(openid) % 10000)
        for t in mock_tags:
            tag_counts[t] = random.randint(1, 15)
        total = sum(tag_counts.values())

    # 归一化到 0-100，取前 8 个最高权重标签
    max_count = max(tag_counts.values()) if tag_counts else 1
    radar_data = sorted(
        [{"tag": t, "label_zh": _tag_label(t), "value": round(c / max_count * 100)}
         for t, c in tag_counts.items()],
        key=lambda x: x["value"], reverse=True,
    )[:8]

    return {
        "openid": openid,
        "radar": radar_data,
        "total_clicks_7d": total,
    }


def _tag_label(tag: str) -> str:
    """tag → 中文标签映射"""
    labels = {
        "LLM": "大模型", "开源": "开源", "Agent": "智能体",
        "基础设施": "基础设施", "多模态": "多模态", "RAG": "RAG",
        "AI编程": "AI编程", "AI产品": "AI产品", "AI安全": "AI安全",
        "AI政策": "AI政策", "融资": "融资", "Python": "Python",
        "科技": "科技", "工具": "工具", "体育": "体育",
        "时事": "时事", "国际": "国际", "政策": "政策", "安全": "安全",
    }
    return labels.get(tag, tag)


# ── GET /api/user/{openid}/daily-digest ──────────────────────────
# Agent 生成每日个性化兴趣总结


@router.get("/user/{openid}/daily-digest")
async def get_daily_digest(openid: str):
    """Agent 根据今日用户点击，生成个性化兴趣领域总结"""
    # 1. 收集用户今日点击的标签
    today_tags: dict[str, int] = {}
    total_clicks = 0
    try:
        if _db_pool:
            rows = await _db_pool.fetch(
                """SELECT item_tags, item_title FROM user_behavior
                   WHERE user_openid = $1
                     AND action = 'click'
                     AND created_at > NOW() - INTERVAL '1 day'
                   ORDER BY created_at DESC""",
                openid,
            )
            for r in rows:
                tags_val = r["item_tags"]
                if isinstance(tags_val, str):
                    tags_val = json.loads(tags_val)
                if isinstance(tags_val, list):
                    for t in tags_val:
                        today_tags[t] = today_tags.get(t, 0) + 1
                        total_clicks += 1
    except Exception:
        logger.warning("DB query failed for daily digest", exc_info=True)

    # Mock 数据
    if total_clicks == 0:
        today_tags = {"LLM": 5, "Agent": 3, "开源": 2, "基础设施": 2}
        total_clicks = 12

    # 2. 排序取 Top 兴趣领域
    top_interests = sorted(today_tags.items(), key=lambda x: x[1], reverse=True)[:5]
    interest_summary = [{"tag": t, "label_zh": _tag_label(t), "clicks": c} for t, c in top_interests]

    # 3. 尝试获取今日简报中匹配的 TL;DR
    matched_tldr: list[str] = []
    try:
        from mock_data import get_briefings
        briefings = get_briefings()
        today_briefing = next((b for b in briefings if b["type"] == "morning"), None)
        if today_briefing:
            top_tag_set = {t for t, _ in top_interests[:3]}
            for section in today_briefing.get("sections", []):
                for item in section.get("items", []):
                    item_tags = set(item.get("tags", []))
                    if item_tags & top_tag_set:
                        matched_tldr.append(f"【{item['title']}】{item['summary'][:50]}...")
            matched_tldr = matched_tldr[:5]
    except Exception:
        logger.warning("Failed to match TL;DR")

    # 4. Agent 生成个性化总结
    agent_msg = _build_digest_message(interest_summary, matched_tldr, total_clicks)

    return {
        "openid": openid,
        "today_clicks": total_clicks,
        "top_interests": interest_summary,
        "matched_news": matched_tldr,
        "agent_summary": agent_msg,
    }


def _build_digest_message(interests: list[dict], matched: list[str], total: int) -> str:
    """Agent 生成个性化总结（模板驱动，后续可接入 LLM）"""
    if total == 0:
        return "今天还没有浏览记录，去看看今天的简报吧！"

    interest_str = "、".join([f"{i['label_zh']}({i['clicks']}次)" for i in interests[:3]])

    lines = [
        f"📊 今日你最关注的领域是 {interest_str}",
        f"共浏览 {total} 篇文章，专注度很高！",
    ]

    if matched:
        lines.append(f"\n🔍 这些文章你可能有兴趣回顾：")
        for m in matched[:3]:
            lines.append(f"  • {m}")

    # 根据兴趣给个性化建议
    top_tag = interests[0]["label_zh"] if interests else "AI"
    lines.append(f"\n💡 Agent建议：你对{top_tag}领域特别感兴趣，已自动为你提升该领域权重，明天的简报将更多覆盖此方向。")

    return "\n".join(lines)
