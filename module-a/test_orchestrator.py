"""TDD: orchestrator.py — 调度器、去重、批量写入测试"""
import uuid
from datetime import datetime, timezone

from orchestrator import dedup_by_url


def test_dedup_empty_list():
    """空列表去重返回空列表"""
    assert dedup_by_url([]) == []


def test_dedup_no_duplicates():
    """无重复时保留全部"""
    items = [
        {"url": "https://a.com/1", "title": "A"},
        {"url": "https://b.com/2", "title": "B"},
        {"url": "https://c.com/3", "title": "C"},
    ]
    result = dedup_by_url(items)
    assert len(result) == 3


def test_dedup_same_source():
    """同源重复 URL：保留第一条"""
    items = [
        {"url": "https://a.com/1", "title": "First", "source": "github"},
        {"url": "https://b.com/2", "title": "Second", "source": "github"},
        {"url": "https://a.com/1", "title": "Duplicate", "source": "github"},
    ]
    result = dedup_by_url(items)
    assert len(result) == 2
    assert result[0]["title"] == "First"


def test_dedup_cross_source():
    """跨源重复 URL：GitHub + HN 引用了同一链接"""
    items = [
        {"url": "https://github.com/vllm/vllm", "title": "vLLM on GitHub", "source": "github"},
        {"url": "https://news.ycombinator.com/item?id=123", "title": "vLLM on HN", "source": "hackernews"},
        {"url": "https://github.com/vllm/vllm", "title": "vLLM again from RSS", "source": "rss"},
    ]
    result = dedup_by_url(items)
    assert len(result) == 2
    sources = {r["source"] for r in result}
    assert "github" in sources


def test_dedup_items_without_url():
    """部分条目无 url：无 url 的按唯一处理（不参与去重）"""
    items = [
        {"title": "no url item", "source": "github"},
        {"url": "https://a.com/1", "title": "Has url", "source": "hackernews"},
    ]
    result = dedup_by_url(items)
    assert len(result) == 2


def test_dedup_preserves_order():
    """去重后保持首次出现的顺序"""
    items = [
        {"url": "https://z.com", "title": "Z"},
        {"url": "https://a.com", "title": "A"},
        {"url": "https://z.com", "title": "Z dup"},
        {"url": "https://m.com", "title": "M"},
    ]
    result = dedup_by_url(items)
    assert [r["title"] for r in result] == ["Z", "A", "M"]


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
