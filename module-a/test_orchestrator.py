"""TDD: orchestrator.py — 调度器、去重、批量写入测试"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

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


# ── run_pipeline ──────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_run_pipeline_empty():
    """空抓取 → 返回 0"""
    from orchestrator import run_pipeline

    pool = AsyncMock()
    with patch("orchestrator.run_all_scrapers", new_callable=AsyncMock,
               return_value=([], {"github": 0, "hackernews": 0, "rss": 0})):
        result = await run_pipeline(pool, datetime.now(timezone.utc), uuid.uuid4(), ["github", "hackernews", "rss"])

    assert result["fetched"] == 0
    assert result["llm_filtered"] is False
    assert "per_source" in result


@pytest.mark.anyio(asyncio_mode="auto")
async def test_run_pipeline_with_llm():
    """Mock 全链路 → 返回 fetched + llm_filtered=True"""
    from orchestrator import run_pipeline

    pool = AsyncMock()
    fake_items = [
        {"title": "Test", "url": "https://a.com/1", "source": "github",
         "content": "", "author": "", "published_at": datetime.now(timezone.utc),
         "batch_id": uuid.uuid4(), "metadata": {}},
    ]

    with patch("orchestrator.run_all_scrapers", new_callable=AsyncMock,
               return_value=(fake_items, {"github": 1, "hackernews": 0, "rss": 0})):
        with patch("llm_filter.filter_and_enrich", new_callable=AsyncMock,
                   return_value=(fake_items, True)):
            with patch("orchestrator.bulk_insert", new_callable=AsyncMock,
                       return_value=1):
                result = await run_pipeline(pool, datetime.now(timezone.utc), uuid.uuid4(), ["github"])

    assert result["fetched"] == 1
    assert result["llm_filtered"] is True
    assert result["per_source"]["github"] == 1


# ── bulk_insert ───────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_bulk_insert_with_embedding():
    """含 embedding 的 items → SQL 参数包含 embedding"""
    from orchestrator import bulk_insert

    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=uuid.uuid4())

    # mock transaction 为 async context manager
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
    mock_transaction.__aexit__ = AsyncMock(return_value=False)
    mock_conn.transaction = MagicMock(return_value=mock_transaction)

    # pool.acquire() 返回 async context manager
    mock_acquire = AsyncMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_acquire

    items = [
        {"source": "github", "title": "Test", "url": "https://a.com/1",
         "content": "", "author": "", "published_at": datetime.now(timezone.utc),
         "batch_id": uuid.uuid4(), "metadata": {}, "embedding": [0.1, 0.2, 0.3]},
    ]
    count = await bulk_insert(mock_pool, items)
    assert count == 1
    mock_conn.fetchval.assert_called_once()


@pytest.mark.anyio(asyncio_mode="auto")
async def test_bulk_insert_without_embedding():
    """无 embedding → embedding 参数为 None"""
    from orchestrator import bulk_insert

    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=uuid.uuid4())

    # mock transaction 为 async context manager
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
    mock_transaction.__aexit__ = AsyncMock(return_value=False)
    mock_conn.transaction = MagicMock(return_value=mock_transaction)

    # pool.acquire() 返回 async context manager
    mock_acquire = AsyncMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_acquire

    items = [
        {"source": "github", "title": "Test", "url": "https://a.com/1",
         "content": "", "author": "", "published_at": datetime.now(timezone.utc),
         "batch_id": uuid.uuid4(), "metadata": {}},
    ]
    count = await bulk_insert(mock_pool, items)
    assert count == 1
    mock_conn.fetchval.assert_called_once()


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
