"""TDD: trend_agent.py — 跨日趋势分析测试"""
import sys
import pytest
from datetime import date, timedelta

sys.path.insert(0, "module-b")
from ai.trend_agent import (
    _tag_label, _extract_all_tags, _detect_anomalies, analyze_trends
)


# ── _tag_label ────────────────────────────────────────────────────────

def test_tag_label_known():
    """已知标签返回中文"""
    assert _tag_label("LLM") == "大模型"
    assert _tag_label("Agent") == "智能体"
    assert _tag_label("RAG") == "RAG"


def test_tag_label_unknown():
    """未知标签原样返回"""
    assert _tag_label("NotExist") == "NotExist"
    assert _tag_label("") == ""


# ── _extract_all_tags ─────────────────────────────────────────────────

def test_extract_all_tags_basic():
    """正常提取标签频次"""
    briefings = [
        {"date": "2026-06-01", "type": "morning", "sections": [
            {"items": [{"tags": ["LLM", "Agent"]}, {"tags": ["LLM"]}]}
        ]},
        {"date": "2026-06-02", "type": "morning", "sections": [
            {"items": [{"tags": ["LLM", "RAG"]}, {"tags": ["Agent"]}]}
        ]},
    ]
    result = _extract_all_tags(briefings, days=2)
    assert result["LLM"] == [2, 1]
    assert result["Agent"] == [1, 1]
    assert result["RAG"] == [0, 1]


def test_extract_all_tags_empty():
    """空简报返回空字典"""
    result = _extract_all_tags([], days=7)
    assert result == {}


def test_extract_all_tags_no_tags():
    """无标签的简报"""
    briefings = [
        {"date": "2026-06-01", "type": "morning", "sections": [
            {"items": [{"tags": []}]}
        ]},
    ]
    result = _extract_all_tags(briefings, days=1)
    assert result == {}


# ── _detect_anomalies ─────────────────────────────────────────────────

def test_detect_anomalies_rising():
    """上升趋势检测"""
    tag_freq = {"Agent": [1, 2, 3, 5, 8, 10, 15]}
    result = _detect_anomalies(tag_freq)
    assert "Agent" in result["rising"]
    assert result["rising"]["Agent"]["change_pct"] > 0


def test_detect_anomalies_falling():
    """下降趋势检测"""
    tag_freq = {"开源": [10, 8, 5, 3, 2, 1, 0]}
    result = _detect_anomalies(tag_freq)
    assert "开源" in result["falling"]


def test_detect_anomalies_new_tag():
    """新标签检测"""
    tag_freq = {"MCP": [0, 0, 0, 0, 0, 0, 5]}
    result = _detect_anomalies(tag_freq)
    assert "MCP" in result["new"]


def test_detect_anomalies_empty():
    """空数据"""
    result = _detect_anomalies({})
    assert result["rising"] == {}
    assert result["falling"] == {}


# ── analyze_trends ────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_analyze_trends_mock():
    """pool=None 时返回 mock 数据"""
    result = await analyze_trends(None, days=7)
    assert "period" in result
    assert "rising" in result
    assert "falling" in result
    assert "new_tags" in result
    assert "agent_insight" in result
    assert "generated_at" in result
    assert len(result["rising"]) > 0


@pytest.mark.anyio(asyncio_mode="auto")
async def test_analyze_trends_mock_days():
    """mock 数据的 period 包含正确天数"""
    result = await analyze_trends(None, days=7)
    start_str, end_str = result["period"].split(" ~ ")
    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)
    assert (end - start).days == 6  # 7 天 = 6 天间隔


@pytest.mark.anyio(asyncio_mode="auto")
async def test_analyze_trends_exception_fallback():
    """异常时回退到 mock"""
    mock_pool = object()  # 不是 asyncpg.Pool，会触发异常
    result = await analyze_trends(mock_pool, days=7)
    assert "rising" in result
    assert "period" in result
