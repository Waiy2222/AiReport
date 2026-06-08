"""TDD: module-b — analyzer/enricher/summarizer/dedup/prompts 测试"""
import sys
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, "module-b")


# ── prompts.py ────────────────────────────────────────────────────────

def test_prompts_constants():
    """所有 Prompt 常量存在"""
    from ai.prompts import (
        SCORING_SYSTEM, DEDUP_SYSTEM, ENRICH_SYSTEM,
        MORNING_SUMMARY_SYSTEM, EVENING_SUMMARY_SYSTEM,
        DEBATE_TECH_PROMPT, DEBATE_BIZ_PROMPT, DEBATE_SOCIAL_PROMPT,
        ARTICLE_SYSTEM,
    )
    assert len(SCORING_SYSTEM) > 50
    assert len(DEDUP_SYSTEM) > 50
    assert len(ENRICH_SYSTEM) > 50
    assert len(MORNING_SUMMARY_SYSTEM) > 50
    assert len(EVENING_SUMMARY_SYSTEM) > 50
    assert len(DEBATE_TECH_PROMPT) > 50
    assert len(DEBATE_BIZ_PROMPT) > 50
    assert len(DEBATE_SOCIAL_PROMPT) > 50


def test_scoring_user():
    """scoring_user 格式化正确"""
    from ai.prompts import scoring_user
    result = scoring_user('[{"index":0,"title":"test"}]')
    assert "test" in result


def test_dedup_user():
    """dedup_user 格式化正确"""
    from ai.prompts import dedup_user
    result = dedup_user('[{"index":0,"title":"test"}]')
    assert "test" in result


def test_enrich_user():
    """enrich_user 格式化正确"""
    from ai.prompts import enrich_user
    result = enrich_user('[{"index":0,"title":"test"}]')
    assert "test" in result


def test_summary_user():
    """summary_user 格式化正确"""
    from ai.prompts import summary_user
    result = summary_user("[]", "morning")
    assert "早报" in result
    result2 = summary_user("[]", "evening")
    assert "晚报" in result2


def test_debate_user():
    """debate_user 格式化正确"""
    from ai.prompts import debate_user
    result = debate_user('{"title":"test"}')
    assert "test" in result


def test_get_summary_system():
    """get_summary_system 返回对应 prompt"""
    from ai.prompts import get_summary_system, MORNING_SUMMARY_SYSTEM, EVENING_SUMMARY_SYSTEM
    assert get_summary_system("morning") == MORNING_SUMMARY_SYSTEM
    assert get_summary_system("evening") == EVENING_SUMMARY_SYSTEM


# ── dedup.py — url_dedup ──────────────────────────────────────────────

def test_url_dedup_basic():
    """URL 去重保留高分"""
    from ai.dedup import url_dedup
    items = [
        {"url": "http://a.com", "ai_score": 5, "title": "A"},
        {"url": "http://a.com", "ai_score": 8, "title": "A better"},
        {"url": "http://b.com", "ai_score": 6, "title": "B"},
    ]
    result = url_dedup(items)
    assert len(result) == 2
    # 保留高分的那条
    a_item = next(r for r in result if r["url"] == "http://a.com")
    assert a_item["ai_score"] == 8


def test_url_dedup_empty():
    """空列表"""
    from ai.dedup import url_dedup
    assert url_dedup([]) == []


def test_url_dedup_no_dup():
    """无重复"""
    from ai.dedup import url_dedup
    items = [
        {"url": "http://a.com", "ai_score": 5},
        {"url": "http://b.com", "ai_score": 6},
    ]
    assert len(url_dedup(items)) == 2


# ── dedup.py — semantic_dedup ─────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_semantic_dedup_empty():
    """空列表"""
    from ai.dedup import semantic_dedup
    assert await semantic_dedup([]) == []


@pytest.mark.anyio(asyncio_mode="auto")
async def test_semantic_dedup_single():
    """单条直接返回"""
    from ai.dedup import semantic_dedup
    items = [{"title": "test"}]
    assert await semantic_dedup(items) == items


@pytest.mark.anyio(asyncio_mode="auto")
async def test_semantic_dedup_api_failure():
    """API 失败时保留全部"""
    from ai.dedup import semantic_dedup
    with patch("ai.dedup.get_client") as mock:
        mock.return_value = AsyncMock()
        mock.return_value.chat.completions.create = AsyncMock(side_effect=Exception("error"))
        items = [{"title": "A", "source": "a"}, {"title": "B", "source": "b"}]
        result = await semantic_dedup(items)
    assert len(result) == 2


# ── analyzer.py — batch_score ─────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_batch_score_empty():
    """空列表"""
    from ai.analyzer import batch_score
    result = await batch_score([])
    assert result == []


@pytest.mark.anyio(asyncio_mode="auto")
async def test_batch_score_api_failure():
    """API 失败时给默认分"""
    from ai.analyzer import batch_score
    with patch("ai.analyzer.get_client") as mock:
        mock.return_value = AsyncMock()
        mock.return_value.chat.completions.create = AsyncMock(side_effect=Exception("error"))
        items = [{"title": "Test", "source": "github", "content": ""}]
        result = await batch_score(items)
    assert len(result) == 1
    assert result[0]["ai_score"] == 5.0
    assert "评分异常" in result[0]["score_reason"]


@pytest.mark.anyio(asyncio_mode="auto")
async def test_batch_score_success():
    """API 成功时解析分数"""
    from ai.analyzer import batch_score
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "scores": [{"index": 0, "score": 8.5, "reason": "重要发布"}]
    })
    with patch("ai.analyzer.get_client") as mock:
        client = AsyncMock()
        client.chat.completions.create = AsyncMock(return_value=mock_resp)
        mock.return_value = client
        items = [{"title": "GPT-5", "source": "github", "content": ""}]
        result = await batch_score(items)
    assert result[0]["ai_score"] == 8.5


# ── enricher.py — enrich ──────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_enrich_empty():
    """空列表"""
    from ai.enricher import enrich
    assert await enrich([]) == []


@pytest.mark.anyio(asyncio_mode="auto")
async def test_enrich_api_failure():
    """API 失败时设默认背景"""
    from ai.enricher import enrich
    with patch("ai.enricher.get_client") as mock:
        mock.return_value = AsyncMock()
        mock.return_value.chat.completions.create = AsyncMock(side_effect=Exception("error"))
        items = [{"title": "Test", "source": "github", "content": ""}]
        result = await enrich(items)
    assert result[0]["background"] == ""


@pytest.mark.anyio(asyncio_mode="auto")
async def test_enrich_success():
    """API 成功时补充背景"""
    from ai.enricher import enrich
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "enriched": [{"index": 0, "background": "这是背景知识"}]
    })
    with patch("ai.enricher.get_client") as mock:
        client = AsyncMock()
        client.chat.completions.create = AsyncMock(return_value=mock_resp)
        mock.return_value = client
        items = [{"title": "Test", "source": "github", "content": ""}]
        result = await enrich(items)
    assert result[0]["background"] == "这是背景知识"


# ── summarizer.py — summarize ─────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_summarize_empty():
    """空列表"""
    from ai.summarizer import summarize
    result = await summarize([], "morning")
    assert result["headline"] == {}
    assert result["tl_dr"] == []
    assert result["sections"] == []
    assert result["key_takeaways"] == []


@pytest.mark.anyio(asyncio_mode="auto")
async def test_summarize_api_failure():
    """API 失败时返回异常提示"""
    from ai.summarizer import summarize
    with patch("ai.summarizer.get_client") as mock:
        mock.return_value = AsyncMock()
        mock.return_value.chat.completions.create = AsyncMock(side_effect=Exception("error"))
        items = [{"title": "Test", "source": "github", "content": ""}]
        result = await summarize(items, "morning")
    assert "处理异常" in result["tl_dr"][0]


@pytest.mark.anyio(asyncio_mode="auto")
async def test_summarize_success():
    """API 成功时返回结构化简报"""
    from ai.summarizer import summarize
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "headline": {"title": "今日AI头条", "summary": "重大发布"},
        "tl_dr": ["要点1", "要点2"],
        "sections": [{"section_title": "AI头条", "items": []}],
        "key_takeaways": ["洞察1"],
    })
    with patch("ai.summarizer.get_client") as mock:
        client = AsyncMock()
        client.chat.completions.create = AsyncMock(return_value=mock_resp)
        mock.return_value = client
        items = [{"title": "Test", "source": "github", "content": ""}]
        result = await summarize(items, "morning")
    assert result["headline"]["title"] == "今日AI头条"
    assert len(result["tl_dr"]) == 2
