"""TDD: source_agent.py — 信源扩展 Agent 测试"""
import sys
import json
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, "module-a")


# ── _has_api_key ──────────────────────────────────────────────────────

def test_has_api_key_false():
    """无 API Key 时返回 False"""
    from source_agent import _has_api_key
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
        assert _has_api_key() is False


def test_has_api_key_true():
    """有效 API Key 时返回 True"""
    from source_agent import _has_api_key
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-test123"}):
        assert _has_api_key() is True


def test_has_api_key_invalid():
    """无效 API Key 时返回 False"""
    from source_agent import _has_api_key
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "invalid-key"}):
        assert _has_api_key() is False


# ── _extract_json ─────────────────────────────────────────────────────

def test_extract_json_fenced():
    """从 ```json 代码块提取"""
    from source_agent import _extract_json
    text = '```json\n[{"tag": "LLM"}]\n```'
    result = _extract_json(text)
    assert json.loads(result) == [{"tag": "LLM"}]


def test_extract_json_plain():
    """纯 JSON 直接返回"""
    from source_agent import _extract_json
    text = '{"tag": "LLM"}'
    result = _extract_json(text)
    assert json.loads(result) == {"tag": "LLM"}


def test_extract_json_nested():
    """嵌套 JSON 提取"""
    from source_agent import _extract_json
    text = '[{"tag": "LLM", "sources": [{"name": "test"}]}]'
    result = _extract_json(text)
    parsed = json.loads(result)
    assert parsed[0]["tag"] == "LLM"


# ── _mock_search_sources ─────────────────────────────────────────────

def test_mock_search_sources():
    """mock 搜索返回候选源列表"""
    from source_agent import _mock_search_sources
    result = _mock_search_sources("LLM")
    assert len(result) > 0
    for src in result:
        assert "name" in src
        assert "url" in src
        assert "rss_url" in src


def test_mock_search_sources_different_tags():
    """不同标签返回不同结果"""
    from source_agent import _mock_search_sources
    llm = _mock_search_sources("LLM")
    sports = _mock_search_sources("体育")
    llm_names = {s["name"] for s in llm}
    sports_names = {s["name"] for s in sports}
    assert llm_names != sports_names


# ── _heuristic_evaluate ───────────────────────────────────────────────

def test_heuristic_evaluate_valid():
    """有效 URL 评估"""
    from source_agent import _heuristic_evaluate
    result = _heuristic_evaluate("https://example.com", "LLM", "大模型")
    assert "authority_score" in result
    assert "freshness_score" in result
    assert "relevance_score" in result
    assert result["authority_score"] >= 0


def test_heuristic_evaluate_empty_url():
    """空 URL 评估"""
    from source_agent import _heuristic_evaluate
    result = _heuristic_evaluate("", "LLM", "大模型")
    assert "authority_score" in result
    assert result["authority_score"] >= 0


# ── _row_to_dict ──────────────────────────────────────────────────────

def test_row_to_dict():
    """行转字典（需要完整的 recommended_sources 字段）"""
    from source_agent import _row_to_dict
    row = {
        "id": 1, "tag": "LLM", "tag_label": "大模型", "name": "test",
        "url": "http://example.com", "rss_url": "http://example.com/rss",
        "quality_score": 4.0, "relevance_score": 3.5,
        "freshness_score": 3.0, "authority_score": 4.0,
        "status": "pending", "discovered_at": None, "approved_at": None,
    }
    result = _row_to_dict(row)
    assert result["id"] == "1"
    assert result["tag"] == "LLM"
    assert result["name"] == "test"


# ── 常量验证 ──────────────────────────────────────────────────────────

def test_coverage_constants():
    """覆盖率阈值常量"""
    from source_agent import COVERAGE_THRESHOLD, COVERAGE_DAYS
    assert COVERAGE_THRESHOLD == 2
    assert COVERAGE_DAYS == 3


def test_functions_exist():
    """所有公开函数存在"""
    import source_agent
    assert callable(source_agent._has_api_key)
    assert callable(source_agent._get_client)
    assert callable(source_agent._llm_chat)
    assert callable(source_agent._extract_json)
    assert callable(source_agent.check_coverage)
    assert callable(source_agent.search_sources)
    assert callable(source_agent._mock_search_sources)
    assert callable(source_agent.evaluate_source)
    assert callable(source_agent._llm_evaluate)
    assert callable(source_agent._heuristic_evaluate)
    assert callable(source_agent.recommend_sources)
    assert callable(source_agent.get_sources_health)
    assert callable(source_agent.get_recommendations)
    assert callable(source_agent.approve_source)
