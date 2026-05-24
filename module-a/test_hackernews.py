"""TDD: scrapers/hackernews.py — Hacker News 抓取测试"""
import uuid
from datetime import datetime, timezone

from scrapers.hackernews import to_raw_items


def test_to_raw_items_maps_fields():
    """to_raw_items 正确映射 HN item 到 raw_items"""
    batch_id = uuid.uuid4()
    items = [
        {
            "title": "DeepSeek-V4 Technical Report",
            "url": "https://news.ycombinator.com/item?id=40000001",
            "by": "tech_review",
            "time": 1717171200,
            "score": 350,
            "descendants": 120,
            "text": "DeepSeek releases V4 with impressive results...",
        }
    ]
    result = to_raw_items(items, batch_id)
    assert len(result) == 1
    r = result[0]
    assert r["source"] == "hackernews"
    assert r["title"] == "DeepSeek-V4 Technical Report"
    assert r["url"] == "https://news.ycombinator.com/item?id=40000001"
    assert r["author"] == "tech_review"
    assert r["published_at"].tzinfo == timezone.utc
    assert r["batch_id"] == batch_id
    assert r["metadata"]["score"] == 350
    assert r["metadata"]["comments"] == 120


def test_to_raw_items_no_url_fallback():
    """无 url 的 HN item 自动构造 HN 链接"""
    batch_id = uuid.uuid4()
    items = [{"title": "Ask HN: AI Tools?", "by": "user1", "time": 1717171200, "score": 10}]
    result = to_raw_items(items, batch_id)
    assert len(result) == 1
    assert result[0]["url"] == ""  # no url and no id → empty


def test_to_raw_items_handles_missing_fields():
    """缺失字段安全降级"""
    batch_id = uuid.uuid4()
    items = [{"title": "Minimal post"}]
    result = to_raw_items(items, batch_id)
    assert len(result) == 1
    r = result[0]
    assert r["url"] == ""
    assert r["author"] == ""
    assert r["content"] == ""
    assert r["metadata"]["score"] == 0
    assert r["metadata"]["comments"] == 0


def test_to_raw_items_empty_list():
    """空列表返回空列表"""
    assert to_raw_items([], uuid.uuid4()) == []


def test_to_raw_items_hackernews_source():
    """所有条目 source 为 hackernews"""
    batch_id = uuid.uuid4()
    items = [
        {"title": "Item 1", "time": 1717171200},
        {"title": "Item 2", "time": 1717171200},
    ]
    result = to_raw_items(items, batch_id)
    assert len(result) == 2
    for r in result:
        assert r["source"] == "hackernews"


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
