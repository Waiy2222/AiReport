"""趋势数据 API 端点 — Phase 3 组员1

路由（在 main.py 中注册）：
- GET /api/trends/weekly     — 近 7 天趋势报告
- GET /api/trends/tag/{tag}  — 单标签 7 天频次曲线
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

# 将 module-b/ai 加入 Python 路径，以便导入 trend_agent
_MODULE_B_AI = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "module-b", "ai"))
if _MODULE_B_AI not in sys.path:
    sys.path.insert(0, _MODULE_B_AI)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["trends"])

# 数据库连接池（由 main.py startup 设置）
_db_pool = None

# tag → 中文标签映射
_TAG_LABELS = {
    "LLM": "大模型", "开源": "开源", "Agent": "智能体",
    "基础设施": "基础设施", "多模态": "多模态", "RAG": "RAG",
    "AI编程": "AI编程", "AI产品": "AI产品", "AI安全": "AI安全",
    "AI政策": "AI政策", "融资": "融资", "Python": "Python",
    "科技": "科技", "工具": "工具", "体育": "体育",
    "时事": "时事", "国际": "国际", "政策": "政策", "安全": "安全",
    "推理": "推理", "MCP": "MCP", "编程": "编程",
    "机器人": "机器人", "芯片": "芯片", "自动驾驶": "自动驾驶",
}


def set_db_pool(pool):
    global _db_pool
    _db_pool = pool


# ── GET /api/trends/weekly ──────────────────────────────────────────


@router.get("/trends/weekly")
async def get_weekly_trends():
    """返回近 7 天趋势报告。DB 不可用时回退到 mock 数据。"""
    try:
        from trend_agent import analyze_trends
        result = await analyze_trends(_db_pool, days=7)
        return result
    except Exception:
        logger.exception("get_weekly_trends failed, using mock fallback")
        return _mock_weekly_trends()


def _mock_weekly_trends() -> dict:
    """内置 mock 趋势数据，不依赖 trend_agent。"""
    today = date.today()
    start = today - timedelta(days=6)
    return {
        "period": f"{start.isoformat()} ~ {today.isoformat()}",
        "rising": [
            {"tag": "Agent", "label_zh": "智能体", "change_pct": 267, "current": 11, "previous": 3},
            {"tag": "多模态", "label_zh": "多模态", "change_pct": 150, "current": 10, "previous": 4},
            {"tag": "芯片", "label_zh": "芯片", "change_pct": 120, "current": 9, "previous": 4},
        ],
        "falling": [
            {"tag": "RAG", "label_zh": "RAG", "change_pct": -60, "current": 2, "previous": 5},
            {"tag": "AI安全", "label_zh": "AI安全", "change_pct": -40, "current": 3, "previous": 5},
        ],
        "new_tags": [
            {"tag": "机器人", "label_zh": "机器人", "first_seen": (today - timedelta(days=1)).isoformat()},
        ],
        "agent_insight": "本周 Agent（智能体）话题热度飙升 267%，ICRA 2026 机器人大会和多家企业发布智能体平台是主要驱动力。多模态持续升温，视频生成和跨模态理解成为新焦点。RAG 热度有所回落，市场关注度转向更具交互性的 Agent 架构。",
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "+00:00",
    }


# ── GET /api/trends/tag/{tag} ───────────────────────────────────────


@router.get("/trends/tag/{tag}")
async def get_tag_trend(tag: str):
    """返回单标签的 7 天频次曲线。"""
    days = 7
    today = date.today()
    start = today - timedelta(days=days - 1)
    dates = [(start + timedelta(days=i)).strftime("%m-%d") for i in range(days)]

    # 尝试从 DB 获取真实数据
    if _db_pool:
        try:
            rows = await _db_pool.fetch(
                """SELECT date, sections FROM briefings
                   WHERE date >= $1 AND date <= $2 AND language = 'zh'
                   ORDER BY date ASC""",
                start, today,
            )
            chart = [0] * days
            date_index = {(start + timedelta(days=i)).isoformat(): i for i in range(days)}
            for r in rows:
                di = date_index.get(r["date"].isoformat())
                if di is None:
                    continue
                sections = r["sections"]
                if isinstance(sections, str):
                    sections = json.loads(sections)
                for section in sections:
                    for item in (section.get("items") or []):
                        if tag in (item.get("tags") or []):
                            chart[di] += 1

            # 检查标签是否存在
            if sum(chart) == 0:
                raise HTTPException(404, f"tag '{tag}' not found in recent briefings")

            return {
                "tag": tag,
                "label_zh": _TAG_LABELS.get(tag, tag),
                "chart": chart,
                "dates": dates,
            }
        except HTTPException:
            raise
        except Exception:
            logger.exception("get_tag_trend DB query failed, using mock")

    # Mock 回退
    mock_charts = {
        "LLM": [5, 6, 7, 8, 9, 10, 11],
        "Agent": [3, 4, 5, 7, 8, 10, 11],
        "多模态": [4, 5, 5, 6, 7, 8, 10],
        "RAG": [5, 5, 4, 3, 3, 2, 2],
    }
    if tag in mock_charts:
        return {
            "tag": tag,
            "label_zh": _TAG_LABELS.get(tag, tag),
            "chart": mock_charts[tag],
            "dates": dates,
        }
    raise HTTPException(404, f"tag '{tag}' not found")
