"""TDD: module-b/ai/pipeline.py — 内部辅助函数测试"""
import sys
import json
import pytest
from datetime import date, datetime, timezone

sys.path.insert(0, "module-b")
from ai.pipeline import (
    _has_api_key, _extract_json, _mock_score_one, _safe_meta,
    _step_filter, _dedup_heuristic, _classify_item, _extract_tags,
    _mock_tldr, _mock_sections, _mock_key_takeaways, _mock_enrich_one,
    _empty_result, _generate_mock,
)


# ── _has_api_key ──────────────────────────────────────────────────────

def test_has_api_key_false():
    """无 API Key 时返回 False"""
    import ai.pipeline as p
    old = p.DEEPSEEK_API_KEY
    p.DEEPSEEK_API_KEY = ""
    assert _has_api_key() is False
    p.DEEPSEEK_API_KEY = old


def test_has_api_key_true():
    """有效 API Key 时返回 True"""
    import ai.pipeline as p
    old = p.DEEPSEEK_API_KEY
    p.DEEPSEEK_API_KEY = "sk-test123"
    assert _has_api_key() is True
    p.DEEPSEEK_API_KEY = old


def test_has_api_key_invalid():
    """无效 API Key 时返回 False"""
    import ai.pipeline as p
    old = p.DEEPSEEK_API_KEY
    p.DEEPSEEK_API_KEY = "invalid-key"
    assert _has_api_key() is False
    p.DEEPSEEK_API_KEY = old


# ── _extract_json ─────────────────────────────────────────────────────

def test_extract_json_fenced():
    """从 ```json 代码块提取"""
    text = '```json\n{"scores": [1,2,3]}\n```'
    result = _extract_json(text)
    assert json.loads(result) == {"scores": [1, 2, 3]}


def test_extract_json_plain():
    """纯 JSON 直接返回"""
    text = '{"scores": [1,2,3]}'
    result = _extract_json(text)
    assert json.loads(result) == {"scores": [1, 2, 3]}


def test_extract_json_nested():
    """嵌套 JSON 提取"""
    text = '[{"index":0,"data":{"score":8}}]'
    result = _extract_json(text)
    parsed = json.loads(result)
    assert parsed[0]["index"] == 0


def test_extract_json_array():
    """JSON 数组提取"""
    text = '[1,2,3]'
    result = _extract_json(text)
    assert json.loads(result) == [1, 2, 3]


# ── _safe_meta ────────────────────────────────────────────────────────

def test_safe_meta_none():
    """metadata 为 None"""
    assert _safe_meta({"metadata": None}) == {}


def test_safe_meta_dict():
    """metadata 为 dict"""
    assert _safe_meta({"metadata": {"score": 8}}) == {"score": 8}


def test_safe_meta_string():
    """metadata 为 JSON 字符串"""
    assert _safe_meta({"metadata": '{"score": 8}'}) == {"score": 8}


def test_safe_meta_missing():
    """无 metadata 字段"""
    assert _safe_meta({}) == {}


def test_safe_meta_invalid_string():
    """无效 JSON 字符串"""
    assert _safe_meta({"metadata": "not json"}) == {}


# ── _mock_score_one ───────────────────────────────────────────────────

def test_mock_score_high_signal():
    """高信号条目得分高"""
    item = {"title": "DeepSeek-V4 正式发布", "content": "重大突破", "source": "github"}
    score = _mock_score_one(item)
    assert score >= 6.0


def test_mock_score_low_signal():
    """低信号条目得分低"""
    item = {"title": "Best hiking trails", "content": "California", "source": "rss"}
    score = _mock_score_one(item)
    assert score <= 6.0


def test_mock_score_clamp():
    """分数在 1-10 范围内"""
    item = {"title": "", "content": "", "source": ""}
    score = _mock_score_one(item)
    assert 1.0 <= score <= 10.0


# ── _step_filter ──────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_step_filter_pass():
    """高于阈值的通过"""
    items = [
        {"metadata": {"ai_score": 8}},
        {"metadata": {"ai_score": 3}},
        {"metadata": {"ai_score": 7}},
    ]
    passed, removed = await _step_filter(items, threshold=6)
    assert len(passed) == 2
    assert len(removed) == 1


@pytest.mark.anyio(asyncio_mode="auto")
async def test_step_filter_empty():
    """空列表"""
    passed, removed = await _step_filter([], threshold=6)
    assert passed == []
    assert removed == []


# ── _dedup_heuristic ──────────────────────────────────────────────────

def test_dedup_heuristic_no_dup():
    """无重复"""
    items = [
        {"title": "GPT-5 发布", "source": "a"},
        {"title": "NBA 总决赛", "source": "b"},
    ]
    kept, removed = _dedup_heuristic(items)
    assert len(kept) == 2
    assert removed == 0


def test_dedup_heuristic_with_dup():
    """标题高度相似的去重"""
    items = [
        {"title": "OpenAI 发布 GPT-5 大模型", "source": "a"},
        {"title": "OpenAI 发布 GPT-5 大语言模型", "source": "b"},
        {"title": "NBA 季后赛结果", "source": "c"},
    ]
    kept, removed = _dedup_heuristic(items)
    assert len(kept) == 2
    assert removed == 1


def test_dedup_heuristic_empty():
    """空列表"""
    kept, removed = _dedup_heuristic([])
    assert kept == []
    assert removed == 0


# ── _classify_item ────────────────────────────────────────────────────

def test_classify_item_llm():
    """LLM 相关分类"""
    item = {"title": "GPT-5 发布", "content": "OpenAI 推出新模型"}
    assert _classify_item(item) == "大模型与开源"


def test_classify_item_agent():
    """Agent 相关分类"""
    item = {"title": "CrewAI 新版本", "content": "智能体框架更新"}
    assert _classify_item(item) == "Agent与智能体"


def test_classify_item_other():
    """无法分类"""
    item = {"title": "天气预报", "content": "今天晴天"}
    assert _classify_item(item) == "其他AI资讯"


# ── _extract_tags ─────────────────────────────────────────────────────

def test_extract_tags_basic():
    """基本标签提取"""
    item = {"title": "DeepSeek 开源 LLM", "content": "大模型发布"}
    tags = _extract_tags(item)
    assert "LLM" in tags
    assert "开源" in tags


def test_extract_tags_max():
    """最多 4 个标签"""
    item = {"title": "GPT Claude Llama DeepSeek Agent RAG MCP", "content": ""}
    tags = _extract_tags(item)
    assert len(tags) <= 4


def test_extract_tags_empty():
    """无匹配标签"""
    item = {"title": "天气预报", "content": "今天晴天"}
    tags = _extract_tags(item)
    assert isinstance(tags, list)


# ── _mock_enrich_one ──────────────────────────────────────────────────

def test_mock_enrich_github():
    """GitHub 来源"""
    item = {"source": "github", "author": "OpenAI"}
    result = _mock_enrich_one(item)
    assert "GitHub" in result


def test_mock_enrich_hackernews():
    """HN 来源"""
    item = {"source": "hackernews"}
    result = _mock_enrich_one(item)
    assert "Hacker News" in result


def test_mock_enrich_other():
    """其他来源"""
    item = {"source": "techcrunch"}
    result = _mock_enrich_one(item)
    assert "techcrunch" in result


# ── _generate_mock ────────────────────────────────────────────────────

def test_generate_mock():
    """mock 生成完整简报"""
    items = [
        {"title": "GPT-5 发布", "content": "OpenAI 推出", "url": "http://a.com",
         "source": "github", "metadata": {"ai_score": 9}},
    ]
    result = _generate_mock(items, "morning", date.today())
    assert "tl_dr" in result
    assert "sections" in result
    assert "key_takeaways" in result
    assert len(result["tl_dr"]) > 0
    assert len(result["sections"]) > 0


def test_mock_tldr():
    """_mock_tldr 返回标题列表"""
    items = [
        {"title": "A", "metadata": {"ai_score": 9}},
        {"title": "B", "metadata": {"ai_score": 5}},
    ]
    result = _mock_tldr(items)
    assert len(result) == 2
    assert result[0] == "A"  # 高分排前面


def test_mock_sections():
    """_mock_sections 按主题分组"""
    items = [
        {"title": "GPT-5 发布", "content": "OpenAI", "url": "http://a.com",
         "source": "github", "metadata": {"ai_score": 9}},
        {"title": "CrewAI 更新", "content": "Agent 框架", "url": "http://b.com",
         "source": "rss", "metadata": {"ai_score": 7}},
    ]
    result = _mock_sections(items)
    assert len(result) >= 1
    for section in result:
        assert "title" in section
        assert "items" in section


def test_mock_key_takeaways():
    """_mock_key_takeaways 返回洞察"""
    items = [{"title": "test"}]
    result = _mock_key_takeaways(items, "morning")
    assert len(result) >= 1
    assert any("早报" in t for t in result)


def test_empty_result():
    """_empty_result 返回有效结构"""
    stats = {"fetched": 0, "scored": 0}
    result = _empty_result(stats, "test reason")
    assert result["status"] == "ok"
    assert "briefing_id" in result
    assert result["stats"] == stats
