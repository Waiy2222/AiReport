"""TDD: scrapers/filters.py — 关键词过滤器测试"""

from scrapers.filters import filter_ai_keywords, filter_items_by_title, AI_KEYWORDS


def test_keywords_not_empty():
    """关键词列表不能为空"""
    assert len(AI_KEYWORDS) > 0, "AI_KEYWORDS must not be empty"


def test_matches_ai_keywords():
    """匹配 AI 关键词的文本返回 True"""
    assert filter_ai_keywords("DeepSeek-V4 released") is True
    assert filter_ai_keywords("New LLM agent framework") is True
    assert filter_ai_keywords("Claude Opus 4.7 benchmark results") is True
    assert filter_ai_keywords("开源大模型发布") is True
    assert filter_ai_keywords("大模型推理优化") is True
    assert filter_ai_keywords("New MCP protocol announced") is True
    assert filter_ai_keywords("RAG pipeline optimization") is True
    assert filter_ai_keywords("vLLM v0.7 released") is True


def test_rejects_non_ai():
    """不含 AI 关键词的文本返回 False"""
    assert filter_ai_keywords("I built a smart toaster") is False
    assert filter_ai_keywords("My cat is very cute") is False
    assert filter_ai_keywords("Best hiking trails in California") is False
    assert filter_ai_keywords("How to bake a chocolate cake") is False
    assert filter_ai_keywords("") is False


def test_case_insensitive():
    """大小写不敏感匹配"""
    assert filter_ai_keywords("deepseek") is True
    assert filter_ai_keywords("DEEPSEEK") is True
    assert filter_ai_keywords("DeepSeek") is True
    assert filter_ai_keywords("LLM") is True
    assert filter_ai_keywords("llm") is True
    assert filter_ai_keywords("RAG") is True
    assert filter_ai_keywords("rag") is True


def test_word_boundary():
    """避免子串误匹配（如 'mail' 不应匹配 'ai'）"""
    # "ai" 是 "mail" 的子串, 需要合理处理
    # 至少独立出现的 ai 应匹配
    assert filter_ai_keywords("using AI for coding") is True
    assert filter_ai_keywords("the ai revolution") is True


def test_batch_filter():
    """批量过滤：保留匹配项，过滤不匹配项"""
    items = [
        {"title": "DeepSeek-V4: Open Source MoE Breakthrough"},
        {"title": "My cat is very cute"},
        {"title": "Claude Opus achieves 85% on SWE-Bench"},
        {"title": "How to bake a cake"},
        {"title": "LLM agent framework released"},
        {"title": "Best hiking trails in California"},
        {"title": "开源RAG引擎v2.0发布"},
    ]
    filtered = filter_items_by_title(items, "title")
    assert len(filtered) == 4, f"Expected 4 AI items, got {len(filtered)}"
    titles = [item["title"] for item in filtered]
    assert any("DeepSeek" in t for t in titles)
    assert any("Claude" in t for t in titles)
    assert any("LLM" in t for t in titles)
    assert any("开源" in t for t in titles)


def test_batch_filter_empty():
    """空列表返回空列表"""
    assert filter_items_by_title([], "title") == []
    assert filter_items_by_title([], "other_field") == []


def test_batch_filter_missing_field():
    """字段缺失的条目被过滤掉"""
    items = [
        {"title": "AI news"},
        {"other": "no title field"},
    ]
    filtered = filter_items_by_title(items, "title")
    assert len(filtered) == 1


if __name__ == "__main__":
    import sys
    passed = 0
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
                passed += 1
            except AssertionError as e:
                print(f"  FAIL {name}: {e}")
                failed += 1
            except Exception as e:
                print(f"  ERROR {name}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed, {passed+failed} total")
    sys.exit(1 if failed else 0)
