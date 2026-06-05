"""TDD: module-c/backend/trends.py — 趋势 API 测试"""
import sys
import pytest
from datetime import date, timedelta

sys.path.insert(0, "module-c/backend")


# ── set_db_pool ───────────────────────────────────────────────────────

def test_set_db_pool():
    """设置数据库池"""
    import trends
    old = trends._db_pool
    trends.set_db_pool("mock_pool")
    assert trends._db_pool == "mock_pool"
    trends.set_db_pool(old)


# ── _mock_weekly_trends ───────────────────────────────────────────────

def test_mock_weekly_trends_structure():
    """mock 数据结构完整"""
    from trends import _mock_weekly_trends
    result = _mock_weekly_trends()
    assert "period" in result
    assert "rising" in result
    assert "falling" in result
    assert "new_tags" in result
    assert "agent_insight" in result
    assert "generated_at" in result


def test_mock_weekly_trends_period():
    """period 包含 7 天"""
    from trends import _mock_weekly_trends
    result = _mock_weekly_trends()
    start_str, end_str = result["period"].split(" ~ ")
    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)
    assert (end - start).days == 6


def test_mock_weekly_trends_rising():
    """rising 非空"""
    from trends import _mock_weekly_trends
    result = _mock_weekly_trends()
    assert len(result["rising"]) > 0
    for item in result["rising"]:
        assert "tag" in item
        assert "label_zh" in item
        assert "change_pct" in item
        assert item["change_pct"] > 0


def test_mock_weekly_trends_falling():
    """falling 非空"""
    from trends import _mock_weekly_trends
    result = _mock_weekly_trends()
    assert len(result["falling"]) > 0
    for item in result["falling"]:
        assert item["change_pct"] < 0


def test_mock_weekly_trends_new_tags():
    """new_tags 非空"""
    from trends import _mock_weekly_trends
    result = _mock_weekly_trends()
    assert len(result["new_tags"]) > 0


def test_mock_weekly_trends_insight():
    """agent_insight 非空"""
    from trends import _mock_weekly_trends
    result = _mock_weekly_trends()
    assert len(result["agent_insight"]) > 50


# ── get_weekly_trends (无 DB) ─────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_get_weekly_trends_no_db():
    """无 DB 时返回 mock 数据"""
    import trends
    old = trends._db_pool
    trends._db_pool = None
    result = await trends.get_weekly_trends()
    trends._db_pool = old
    assert "rising" in result
    assert "period" in result


# ── get_tag_trend (无 DB) ─────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_get_tag_trend_llm():
    """LLM 标签趋势（mock）"""
    import trends
    old = trends._db_pool
    trends._db_pool = None
    result = await trends.get_tag_trend("LLM")
    trends._db_pool = old
    assert result["tag"] == "LLM"
    assert result["label_zh"] == "大模型"
    assert len(result["chart"]) == 7
    assert len(result["dates"]) == 7


@pytest.mark.anyio(asyncio_mode="auto")
async def test_get_tag_trend_agent():
    """Agent 标签趋势（mock）"""
    import trends
    old = trends._db_pool
    trends._db_pool = None
    result = await trends.get_tag_trend("Agent")
    trends._db_pool = old
    assert result["tag"] == "Agent"
    assert result["label_zh"] == "智能体"


@pytest.mark.anyio(asyncio_mode="auto")
async def test_get_tag_trend_not_found():
    """不存在的标签 → 404"""
    import trends
    from fastapi import HTTPException
    old = trends._db_pool
    trends._db_pool = None
    with pytest.raises(HTTPException) as exc_info:
        await trends.get_tag_trend("NotExist")
    trends._db_pool = old
    assert exc_info.value.status_code == 404


# ── _TAG_LABELS ───────────────────────────────────────────────────────

def test_tag_labels():
    """标签映射完整"""
    import trends
    assert trends._TAG_LABELS["LLM"] == "大模型"
    assert trends._TAG_LABELS["Agent"] == "智能体"
    assert trends._TAG_LABELS["RAG"] == "RAG"
    assert len(trends._TAG_LABELS) >= 20


# ── router ────────────────────────────────────────────────────────────

def test_router_prefix():
    """路由前缀正确"""
    import trends
    assert trends.router.prefix == "/api"
