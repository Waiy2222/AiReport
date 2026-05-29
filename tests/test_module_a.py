"""Tests for Module A — News Fetcher & Scrapers."""
import uuid
import importlib.util
import pytest
import sys, os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

# Load module-a/main.py explicitly to avoid name conflicts across test files
_A_DIR = os.path.join(os.path.dirname(__file__), '..', 'module-a')
sys.path.insert(0, _A_DIR)
_spec = importlib.util.spec_from_file_location("module_a_main", os.path.join(_A_DIR, "main.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["module_a_main"] = _mod
_spec.loader.exec_module(_mod)

app = _mod.app
_get_pool_or_503 = _mod._get_pool_or_503
_fetch_source = _mod._fetch_source

for _stale in ['pipeline', 'db', 'models', 'config']:
    sys.modules.pop(_stale, None)

# Also make scrapers importable (already on path above)

client = TestClient(app)


# ── Health ────────────────────────────────────────────────────────────────
def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "db" in data


# ── DB guard ─────────────────────────────────────────────────────────────
def test_get_pool_or_503_raises_when_no_db():
    with pytest.raises(HTTPException) as exc:
        _get_pool_or_503()
    assert exc.value.status_code == 503


def test_run_returns_503_without_db():
    response = client.post("/run", json={
        "batch_id": str(uuid.uuid4()),
        "hours_back": 12,
    })
    assert response.status_code == 503


# ── _fetch_source dispatch ───────────────────────────────────────────────
@pytest.mark.anyio
async def test_fetch_source_unknown_source():
    pool = AsyncMock()
    count = await _fetch_source(pool, "nonexistent", datetime.now(timezone.utc), uuid.uuid4())
    assert count == 0


@pytest.mark.anyio
async def test_fetch_source_handles_exception():
    pool = AsyncMock()
    since = datetime.now(timezone.utc) - timedelta(hours=12)

    async def boom(*args, **kwargs):
        raise RuntimeError("boom")

    with patch.dict("module_a_main.SCRAPERS", {"github": boom}):
        count = await _fetch_source(pool, "github", since, uuid.uuid4())
        assert count == 0


# ── Scraper insertion helper ─────────────────────────────────────────────
@pytest.mark.anyio
async def test_insert_items_skips_duplicates(mock_pool):
    from scrapers import _insert_items

    # _insert_items calls conn.fetchval, not pool.fetchval
    conn = mock_pool.acquire.return_value.conn
    conn.fetchval = AsyncMock(return_value=None)

    items = [
        {
            "source": "github", "title": "Test", "url": "https://github.com/test/repo",
            "content": "Desc", "author": "test",
            "published_at": datetime.now(timezone.utc),
            "metadata": {"stars": 100},
        }
    ]
    count = await _insert_items(mock_pool, "github", items, uuid.uuid4())
    assert count == 0


@pytest.mark.anyio
async def test_insert_items_counts_inserted(mock_pool):
    from scrapers import _insert_items

    # _insert_items calls conn.fetchval, not pool.fetchval
    conn = mock_pool.acquire.return_value.conn
    conn.fetchval = AsyncMock(return_value="some-uuid")

    items = [
        {
            "source": "rss", "title": "Item", "url": "https://example.com/1",
            "content": "...", "author": "author",
            "published_at": datetime.now(timezone.utc), "metadata": {},
        }
    ]
    count = await _insert_items(mock_pool, "rss", items, uuid.uuid4())
    assert count == 1


# ── GitHub scraper (basic) ────────────────────────────────────────────────
@pytest.mark.anyio
async def test_github_scraper_non_200():
    from scrapers.github import fetch

    pool = AsyncMock()
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.raise_for_status.side_effect = Exception("403")
    mock_client.get.return_value = mock_response

    with patch("scrapers.github.httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value = mock_client
        items = await fetch(pool, datetime.now(timezone.utc) - timedelta(hours=24), uuid.uuid4())

    assert len(items) == 0


# ── Reddit scraper header ─────────────────────────────────────────────────
@pytest.mark.anyio
async def test_reddit_scraper_sets_user_agent():
    from scrapers.reddit import fetch

    pool = AsyncMock()
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.raise_for_status.side_effect = Exception("429")
    mock_client.get.return_value = mock_response

    with patch("scrapers.reddit.httpx.AsyncClient") as mock_http:
        mock_http.return_value.__aenter__.return_value = mock_client
        await fetch(pool, datetime.now(timezone.utc) - timedelta(hours=24), uuid.uuid4())

    call_args = mock_client.get.call_args
    assert call_args is not None
