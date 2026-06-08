"""TDD: scrapers/rss.py — RSS 资讯抓取测试"""
import uuid
from datetime import datetime, timezone, timedelta

from scrapers.rss import to_raw_items, RSS_SOURCES


def test_rss_sources_not_empty():
    """RSS 源列表至少包含已知的 5 个源"""
    assert len(RSS_SOURCES) >= 5
    names = [s["name"] for s in RSS_SOURCES]
    assert "huggingface_blog" in names
    assert "36kr" in names


def test_rss_sources_have_required_keys():
    """每个 RSS 源配置包含 name 和 url"""
    for src in RSS_SOURCES:
        assert "name" in src, f"Missing 'name' in {src}"
        assert "url" in src, f"Missing 'url' in {src}"
        assert src["url"].startswith("http"), f"Invalid URL: {src['url']}"


def test_to_raw_items_maps_fields():
    """to_raw_items 正确映射 RSS entry 到 raw_items"""
    batch_id = uuid.uuid4()
    entries = [
        {
            "title": "DeepSeek-V4 Technical Report Released",
            "link": "https://arxiv.org/abs/2605.00001",
            "summary": "DeepSeek releases V4 with MoE architecture, 370B parameters.",
            "author": "DeepSeek Team",
            "published_parsed": (2026, 5, 23, 10, 0, 0, 0, 143, 0),
        }
    ]
    result = to_raw_items(entries, "arxiv", batch_id)
    assert len(result) == 1
    r = result[0]
    assert r["source"] == "arxiv"
    assert r["title"] == "DeepSeek-V4 Technical Report Released"
    assert r["url"] == "https://arxiv.org/abs/2605.00001"
    assert "DeepSeek releases V4" in r["content"]
    assert r["author"] == "DeepSeek Team"
    assert r["published_at"].tzinfo == timezone.utc
    assert r["batch_id"] == batch_id
    assert isinstance(r["metadata"], dict)


def test_to_raw_items_handles_missing_fields():
    """RSS entry 缺少字段时安全降级"""
    batch_id = uuid.uuid4()
    entries = [{"title": "Just a title"}]
    result = to_raw_items(entries, "test-source", batch_id)
    assert len(result) == 1
    r = result[0]
    assert r["url"] == ""  # 缺 link → 空字符串
    assert r["content"] == ""  # 缺 summary → 空字符串
    assert r["author"] == ""  # 缺 author → 空字符串
    assert r["source"] == "test-source"


def test_to_raw_items_empty_list():
    """空条目列表返回空列表"""
    assert to_raw_items([], "arxiv", uuid.uuid4()) == []


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
