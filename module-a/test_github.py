"""TDD: scrapers/github.py — GitHub 资讯抓取测试"""
import uuid
from datetime import datetime, timezone, timedelta

from scrapers.github import build_query, to_raw_items


def test_build_query_returns_string():
    """build_query 返回非空查询字符串"""
    since = datetime(2026, 5, 23, tzinfo=timezone.utc)
    q = build_query(since)
    assert isinstance(q, str)
    assert len(q) > 0


def test_build_query_includes_date():
    """查询字符串包含 created:>YYYY-MM-DD 过滤"""
    since = datetime(2026, 5, 23, tzinfo=timezone.utc)
    q = build_query(since)
    assert "created:>2026-05-23" in q


def test_build_query_includes_ai_keywords():
    """查询字符串包含 AI 关键词"""
    since = datetime(2026, 5, 23, tzinfo=timezone.utc)
    q = build_query(since)
    assert "AI" in q or "ai" in q.lower() or "agent" in q.lower() or "llm" in q.lower()


def test_to_raw_items_maps_fields():
    """to_raw_items 正确映射 GitHub API 响应字段到 raw_items"""
    batch_id = uuid.uuid4()
    items = [
        {
            "full_name": "langchain-ai/langchain",
            "html_url": "https://github.com/langchain-ai/langchain",
            "description": "Build AI agent applications with LLMs",
            "owner": {"login": "langchain-ai"},
            "created_at": "2026-05-23T10:00:00Z",
            "stargazers_count": 50000,
            "forks_count": 5000,
            "language": "Python",
            "topics": ["llm", "ai", "agent"],
        }
    ]
    result = to_raw_items(items, batch_id)
    assert len(result) == 1
    r = result[0]
    assert r["source"] == "github"
    assert r["title"] == "langchain-ai/langchain"
    assert r["url"] == "https://github.com/langchain-ai/langchain"
    assert r["content"] == "Build AI agent applications with LLMs"
    assert r["author"] == "langchain-ai"
    assert r["published_at"].tzinfo == timezone.utc
    assert r["batch_id"] == batch_id
    assert isinstance(r["metadata"], dict)
    assert r["metadata"]["stars"] == 50000
    assert r["metadata"]["forks"] == 5000
    assert r["metadata"]["language"] == "Python"
    assert r["metadata"]["topics"] == ["llm", "ai", "agent"]


def test_to_raw_items_handles_missing_fields():
    """缺失字段时安全降级（不崩溃）"""
    batch_id = uuid.uuid4()
    items = [
        {
            "full_name": "test/repo",
            "html_url": "https://github.com/test/repo",
            "description": None,
            "owner": None,
            "created_at": "2026-05-23T10:00:00Z",
            "stargazers_count": 0,
            "forks_count": 0,
            "language": None,
            "topics": [],
        }
    ]
    result = to_raw_items(items, batch_id)
    assert len(result) == 1
    r = result[0]
    assert r["content"] == ""  # None → empty string
    assert r["author"] == ""  # None owner → empty string


def test_to_raw_items_empty_list():
    """空输入返回空列表"""
    assert to_raw_items([], uuid.uuid4()) == []


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
