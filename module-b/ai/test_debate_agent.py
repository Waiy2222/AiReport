"""TDD: debate_agent.py — 多智能体辩论测试"""
import json
import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# 添加 module-b 到路径，使相对导入能工作
sys.path.insert(0, "module-b")
from ai.debate_agent import (
    _build_item_json, run_debate, DEBATE_THRESHOLD, PERSONAS
)


# ── _build_item_json ──────────────────────────────────────────────────

def test_build_item_json_basic():
    """基本字段映射正确"""
    item = {
        "title": "GPT-5 发布",
        "content": "OpenAI 发布 GPT-5，性能大幅提升" * 20,  # 超长内容
        "source": "techcrunch",
        "ai_score": 9,
        "tags": ["LLM", "AI产品"],
    }
    result = json.loads(_build_item_json(item))
    assert result["title"] == "GPT-5 发布"
    assert result["source"] == "techcrunch"
    assert result["ai_score"] == 9
    assert result["tags"] == ["LLM", "AI产品"]
    assert len(result["content"]) <= 300  # 内容被截断


def test_build_item_json_missing_fields():
    """缺少字段时安全降级"""
    item = {"title": "Test"}
    result = json.loads(_build_item_json(item))
    assert result["title"] == "Test"
    assert result["content"] == ""
    assert result["source"] == ""
    assert result["ai_score"] == 0
    assert result["tags"] == []


def test_build_item_json_empty():
    """空字典"""
    result = json.loads(_build_item_json({}))
    assert result["title"] == ""
    assert result["ai_score"] == 0


# ── run_debate ────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_run_debate_empty():
    """空列表 → 直接返回"""
    result = await run_debate([])
    assert result == []


@pytest.mark.anyio(asyncio_mode="auto")
async def test_run_debate_below_threshold():
    """低于阈值的新闻不跑辩论"""
    items = [
        {"title": "普通新闻", "ai_score": 5, "metadata": {}},
        {"title": "低分新闻", "ai_score": 3, "metadata": {}},
    ]
    result = await run_debate(items)
    assert len(result) == 2
    for item in result:
        assert "debate" not in item.get("metadata", {})


@pytest.mark.anyio(asyncio_mode="auto")
async def test_run_debate_above_threshold():
    """高于阈值的新闻跑辩论（mock LLM）"""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "这是一个重要的技术突破"

    with patch("ai.debate_agent.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        items = [
            {"title": "重大突破", "ai_score": 9, "metadata": {}, "content": "test"},
        ]
        result = await run_debate(items)

    assert len(result) == 1
    debate = result[0]["metadata"]["debate"]
    assert "tech_view" in debate
    assert "biz_view" in debate
    assert "social_view" in debate
    assert "consensus" in debate
    assert "controversy" in debate


@pytest.mark.anyio(asyncio_mode="auto")
async def test_run_debate_llm_failure():
    """LLM 调用失败时回退到默认值"""
    with patch("ai.debate_agent.get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
        mock_get_client.return_value = mock_client

        items = [
            {"title": "重大新闻", "ai_score": 10, "metadata": {}, "content": "test"},
        ]
        result = await run_debate(items)

    assert len(result) == 1
    debate = result[0]["metadata"]["debate"]
    assert "暂不可用" in debate["tech_view"]
    assert debate["controversy"] == 0  # 三方都失败，无有效观点


def test_debate_threshold_constant():
    """辩论阈值为 8"""
    assert DEBATE_THRESHOLD == 8


def test_personas_count():
    """3 个辩论角色"""
    assert len(PERSONAS) == 3
    names = [p[0] for p in PERSONAS]
    assert "Tech-Agent" in names
    assert "Biz-Agent" in names
    assert "Social-Agent" in names
