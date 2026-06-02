"""跨日趋势分析 Agent — Phase 3 组员1

分析近 N 天简报数据，发现标签热度变化趋势，生成趋势报告。
无 DB 或无 API Key 时自动回退到 mock 数据。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# tag → 中文标签映射（与 module-c/backend/tags.py 保持一致）
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


def _tag_label(tag: str) -> str:
    return _TAG_LABELS.get(tag, tag)


# ── 主入口 ──────────────────────────────────────────────────────────


async def analyze_trends(pool: asyncpg.Pool | None, days: int = 7) -> dict[str, Any]:
    """主入口：分析近 N 天趋势，返回完整趋势报告。

    返回格式：
    {
        "period": "2026-05-27 ~ 2026-06-02",
        "rising": [{"tag": "Agent", "label_zh": "智能体", "change_pct": 267, "current": 11, "previous": 3}],
        "falling": [...],
        "new_tags": [...],
        "agent_insight": "...",
        "generated_at": "2026-06-02T20:00:00+00:00"
    }
    """
    try:
        if pool is None:
            return _mock_trends(days)

        briefings = await _fetch_briefing_history(pool, days)
        if not briefings:
            logger.warning("No briefings found in last %d days, using mock", days)
            return _mock_trends(days)

        tag_freq = _extract_all_tags(briefings, days)
        anomalies = _detect_anomalies(tag_freq)
        insight = await _call_llm_trend_analysis(tag_freq, anomalies)

        today = date.today()
        start = today - timedelta(days=days - 1)
        period = f"{start.isoformat()} ~ {today.isoformat()}"

        return {
            "period": period,
            "rising": [
                {"tag": t, "label_zh": _tag_label(t), "change_pct": d["change_pct"],
                 "current": d["current"], "previous": d["previous"]}
                for t, d in anomalies.get("rising", {}).items()
            ],
            "falling": [
                {"tag": t, "label_zh": _tag_label(t), "change_pct": d["change_pct"],
                 "current": d["current"], "previous": d["previous"]}
                for t, d in anomalies.get("falling", {}).items()
            ],
            "new_tags": [
                {"tag": t, "label_zh": _tag_label(t), "first_seen": d["first_seen"]}
                for t, d in anomalies.get("new", {}).items()
            ],
            "agent_insight": insight or "本周暂无显著趋势变化。",
            "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "+00:00",
        }
    except Exception:
        logger.exception("analyze_trends failed, falling back to mock")
        return _mock_trends(days)


# ── 内部函数 ────────────────────────────────────────────────────────


async def _fetch_briefing_history(pool: asyncpg.Pool, days: int) -> list[dict]:
    """从 briefings 表查询近 N 天的 morning + evening 简报。"""
    today = date.today()
    start = today - timedelta(days=days - 1)
    rows = await pool.fetch(
        """SELECT type, date, sections
           FROM briefings
           WHERE date >= $1 AND date <= $2 AND language = 'zh'
           ORDER BY date ASC, type ASC""",
        start, today,
    )
    result = []
    for r in rows:
        sections = r["sections"]
        if isinstance(sections, str):
            import json
            sections = json.loads(sections)
        result.append({
            "date": r["date"].isoformat(),
            "type": r["type"],
            "sections": sections,
        })
    return result


def _extract_all_tags(briefings: list[dict], days: int) -> dict[str, list[int]]:
    """统计每个 tag 在每个日期的出现次数。

    返回：{"LLM": [3,5,5,8,9,11,11], "Agent": [1,2,3,5,5,7,8], ...}
    数组第 0 个 = 最早一天。
    """
    # 构建日期索引
    date_set = sorted({b["date"] for b in briefings})
    date_index = {d: i for i, d in enumerate(date_set)}

    tag_freq: dict[str, list[int]] = {}
    for b in briefings:
        di = date_index.get(b["date"])
        if di is None:
            continue
        for section in b.get("sections", []):
            for item in (section.get("items") or []):
                for tag in (item.get("tags") or []):
                    if tag not in tag_freq:
                        tag_freq[tag] = [0] * len(date_set)
                    tag_freq[tag][di] += 1
    return tag_freq


def _detect_anomalies(tag_freq: dict[str, list[int]]) -> dict[str, dict]:
    """对比最新一天和 7 天前的频次，分类为 rising/falling/new/stable。"""
    result = {"rising": {}, "falling": {}, "new": {}, "stable": {}}

    for tag, freq in tag_freq.items():
        current = freq[-1] if freq else 0
        previous = freq[0] if freq else 0

        if previous == 0 and current > 0:
            # 新出现的标签，找到首次出现的日期索引
            first_idx = next((i for i, v in enumerate(freq) if v > 0), 0)
            result["new"][tag] = {
                "first_seen_index": first_idx,
                "first_seen": "",
                "current": current,
            }
        elif previous == 0:
            continue
        else:
            change_pct = round((current - previous) / previous * 100)
            entry = {"change_pct": change_pct, "current": current, "previous": previous}
            if change_pct > 30:
                result["rising"][tag] = entry
            elif change_pct < -30:
                result["falling"][tag] = entry
            else:
                result["stable"][tag] = entry

    # 按变化幅度排序，取 top 5
    result["rising"] = dict(
        sorted(result["rising"].items(), key=lambda x: -x[1]["change_pct"])[:5]
    )
    result["falling"] = dict(
        sorted(result["falling"].items(), key=lambda x: x[1]["change_pct"])[:5]
    )
    result["new"] = dict(list(result["new"].items())[:5])

    return result


async def _call_llm_trend_analysis(
    tag_freq: dict[str, list[int]], anomalies: dict
) -> str | None:
    """调用 LLM 生成趋势解读文字（100-150 字中文）。"""
    from pipeline import _llm_chat

    # 构建频次摘要
    freq_summary = []
    for tag, freq in sorted(tag_freq.items(), key=lambda x: -x[1][-1]):
        freq_summary.append(f"  {tag}({_tag_label(tag)}): {'→'.join(map(str, freq))}")

    rising_tags = list(anomalies.get("rising", {}).keys())
    falling_tags = list(anomalies.get("falling", {}).keys())
    new_tags = list(anomalies.get("new", {}).keys())

    prompt = f"""你是一位 AI 行业趋势分析师。以下是近 7 天 AI 资讯简报中各标签的逐日频次统计：

{chr(10).join(freq_summary[:20])}

变化摘要：
- 热度飙升：{', '.join(rising_tags) if rising_tags else '无'}
- 热度降温：{', '.join(falling_tags) if falling_tags else '无'}
- 新兴标签：{', '.join(new_tags) if new_tags else '无'}

请用 100-150 字中文解读本周 AI 行业趋势，重点分析飙升和降温标签背后的原因，语气专业但通俗易懂。"""

    messages = [
        {"role": "system", "content": "你是 AI 行业趋势分析师，用简洁专业的中文回答。"},
        {"role": "user", "content": prompt},
    ]
    return await _llm_chat(messages, temperature=0.7, max_tokens=500)


def _mock_trends(days: int = 7) -> dict[str, Any]:
    """无 DB/API Key 时返回预设的 mock 趋势数据。"""
    today = date.today()
    start = today - timedelta(days=days - 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(days)]

    return {
        "period": f"{dates[0]} ~ {dates[-1]}",
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
            {"tag": "机器人", "label_zh": "机器人", "first_seen": dates[-2]},
        ],
        "agent_insight": (
            "本周 Agent（智能体）话题热度飙升 267%，ICRA 2026 机器人大会和多家企业发布"
            "智能体平台是主要驱动力。多模态持续升温，视频生成和跨模态理解成为新焦点。"
            "RAG 热度有所回落，市场关注度转向更具交互性的 Agent 架构。"
        ),
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "+00:00",
    }
