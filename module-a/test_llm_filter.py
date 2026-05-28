"""TDD: llm_filter.py — LLM 智能筛选模块测试"""
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest


# ── _has_api_key ──────────────────────────────────────────────────────────

def test_has_api_key_false(monkeypatch):
    """无 API Key → False"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from llm_filter import _has_api_key
    assert _has_api_key() is False


def test_has_api_key_true(monkeypatch):
    """有 API Key → True"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test123456")
    from llm_filter import _has_api_key
    assert _has_api_key() is True


# ── _extract_json ─────────────────────────────────────────────────────────

def test_extract_json_fenced():
    """处理 ```json 包裹"""
    from llm_filter import _extract_json
    input_text = '```json\n[{"index": 0, "score": 8}]\n```'
    result = _extract_json(input_text)
    assert result == '[{"index": 0, "score": 8}]'


def test_extract_json_plain():
    """纯 JSON 不变"""
    from llm_filter import _extract_json
    input_text = '[{"index": 0, "score": 8}]'
    result = _extract_json(input_text)
    assert result == '[{"index": 0, "score": 8}]'


def test_extract_json_nested():
    """嵌套 JSON 正确提取"""
    from llm_filter import _extract_json
    input_text = 'some text [{"index": 0, "data": {"score": 8}}] end'
    result = _extract_json(input_text)
    assert '"index"' in result
    assert result.startswith("[")
    assert result.endswith("]")


# ── _mock_score_one ───────────────────────────────────────────────────────

def test_mock_score_high_signal():
    """高信号条目 → score >= 7"""
    from llm_filter import _mock_score_one
    item = {"title": "DeepSeek-V4 开源发布", "content": "重大突破", "source": "github"}
    score = _mock_score_one(item)
    assert score >= 7.0, f"Expected >= 7.0, got {score}"


def test_mock_score_low_signal():
    """无关条目 → score <= 5"""
    from llm_filter import _mock_score_one
    item = {"title": "Best hiking trails in California", "content": "Nature guide", "source": "rss"}
    score = _mock_score_one(item)
    assert score <= 5.0, f"Expected <= 5.0, got {score}"


def test_mock_score_medium():
    """一般技术讨论 → 5 <= score <= 7"""
    from llm_filter import _mock_score_one
    item = {"title": "Python web framework released", "content": "new version update", "source": "hackernews"}
    score = _mock_score_one(item)
    assert 5.0 <= score <= 7.0, f"Expected 5.0-7.0, got {score}"


# ── _build_filter_prompt ──────────────────────────────────────────────────

def test_build_prompt_contains_items():
    """prompt 包含条目标题"""
    from llm_filter import _build_filter_prompt
    items = [
        {"title": "GPT-5 released", "source": "github", "content": "OpenAI released GPT-5"},
        {"title": "New RAG framework", "source": "hackernews", "content": "A new framework"},
    ]
    prompt = _build_filter_prompt(items, rag_context="")
    assert "GPT-5 released" in prompt
    assert "New RAG framework" in prompt


def test_build_prompt_contains_rag():
    """prompt 包含 RAG 上下文"""
    from llm_filter import _build_filter_prompt
    items = [{"title": "Test", "source": "github", "content": "Test content"}]
    rag_ctx = "- [github] Similar item (相似度:0.95, 标签:LLM)"
    prompt = _build_filter_prompt(items, rag_context=rag_ctx)
    assert "参考历史案例" in prompt
    assert "Similar item" in prompt


def test_build_prompt_contains_criteria():
    """prompt 包含评分标准"""
    from llm_filter import _build_filter_prompt
    items = [{"title": "Test", "source": "github", "content": "Test"}]
    prompt = _build_filter_prompt(items, rag_context="")
    assert "评分标准" in prompt
    assert "10分" in prompt
    assert "1-3分" in prompt


# ── filter_and_enrich ─────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_filter_enrich_fallback(monkeypatch):
    """无 API Key → 返回 (scored_items, False)"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from llm_filter import filter_and_enrich

    pool = AsyncMock()
    items = [
        {"title": "DeepSeek-V4 开源", "content": "重大突破", "source": "github",
         "url": "https://github.com/test/1", "author": "test",
         "published_at": datetime.now(timezone.utc), "batch_id": uuid.uuid4(),
         "metadata": {}},
        {"title": "Best hiking trails", "content": "Nature", "source": "rss",
         "url": "https://example.com/2", "author": "test",
         "published_at": datetime.now(timezone.utc), "batch_id": uuid.uuid4(),
         "metadata": {}},
    ]
    passed, used_llm = await filter_and_enrich(pool, items)
    assert used_llm is False
    assert len(passed) >= 1  # 至少高分条目通过


@pytest.mark.anyio(asyncio_mode="auto")
async def test_filter_enrich_with_llm(monkeypatch):
    """Mock LLM → 返回 (filtered_items, True)"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test123456")
    from llm_filter import filter_and_enrich

    pool = AsyncMock()
    items = [
        {"title": "GPT-5 released", "content": "Major release", "source": "github",
         "url": "https://github.com/test/1", "author": "test",
         "published_at": datetime.now(timezone.utc), "batch_id": uuid.uuid4(),
         "metadata": {}},
    ]

    mock_llm_response = '[{"index": 0, "score": 9.0, "tags": ["LLM"], "reason": "Major release"}]'

    with patch("llm_filter._llm_chat", new_callable=AsyncMock, return_value=mock_llm_response):
        with patch("shared.rag.generate_embeddings_batch", new_callable=AsyncMock,
                   return_value=[[0.1] * 1536]):
            with patch("shared.rag.search_similar_items", new_callable=AsyncMock,
                       return_value=[]):
                passed, used_llm = await filter_and_enrich(pool, items)

    assert used_llm is True
    assert len(passed) == 1
    assert passed[0]["metadata"]["ai_score"] == 9.0
    assert "LLM" in passed[0]["metadata"]["tags"]


@pytest.mark.anyio(asyncio_mode="auto")
async def test_filter_threshold(monkeypatch):
    """threshold=8.0 过滤低分条目"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from llm_filter import filter_and_enrich

    pool = AsyncMock()
    items = [
        {"title": "DeepSeek-V4 开源发布", "content": "重大突破性进展", "source": "github",
         "url": "https://github.com/test/1", "author": "test",
         "published_at": datetime.now(timezone.utc), "batch_id": uuid.uuid4(),
         "metadata": {}},
        {"title": "Random blog post", "content": "Nothing interesting", "source": "rss",
         "url": "https://example.com/2", "author": "test",
         "published_at": datetime.now(timezone.utc), "batch_id": uuid.uuid4(),
         "metadata": {}},
    ]
    passed, _ = await filter_and_enrich(pool, items, threshold=8.0)
    for item in passed:
        assert item["metadata"]["ai_score"] >= 8.0


@pytest.mark.anyio(asyncio_mode="auto")
async def test_filter_enrich_embedding(monkeypatch):
    """通过的条目有 embedding 字段"""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from llm_filter import filter_and_enrich

    pool = AsyncMock()
    items = [
        {"title": "DeepSeek-V4 开源发布重大突破", "content": "AI 领域重大进展",
         "source": "github", "url": "https://github.com/test/1", "author": "test",
         "published_at": datetime.now(timezone.utc), "batch_id": uuid.uuid4(),
         "metadata": {}},
    ]

    with patch("shared.rag.generate_embeddings_batch", new_callable=AsyncMock,
               return_value=[[0.1] * 1536]):
        passed, _ = await filter_and_enrich(pool, items)

    for item in passed:
        assert "embedding" in item, f"Item missing embedding: {item['title']}"
        assert item["embedding"] is not None


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
