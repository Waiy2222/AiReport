"""Tests for Module B — AI Content Processing Pipeline."""
import uuid
import importlib.util
import pytest
import sys, os
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

_B_DIR = os.path.join(os.path.dirname(__file__), '..', 'module-b')
sys.path.insert(0, _B_DIR)
_spec = importlib.util.spec_from_file_location("module_b_main", os.path.join(_B_DIR, "main.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["module_b_main"] = _mod
_spec.loader.exec_module(_mod)

app = _mod.app
_get_pool_or_503 = _mod._get_pool_or_503

for _stale in ['pipeline', 'db', 'models', 'config']:
    sys.modules.pop(_stale, None)

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_pool_or_503_raises_when_no_db():
    with pytest.raises(HTTPException) as exc:
        _get_pool_or_503()
    assert exc.value.status_code == 503


def test_run_b_returns_503_without_db():
    response = client.post("/run-b", json={
        "type": "morning", "date": "2026-05-24",
        "batch_id": str(uuid.uuid4()),
    })
    assert response.status_code == 503


def test_run_b_rejects_invalid_type():
    # run_pipeline is imported inside run_b via `from ai.pipeline import run_pipeline`
    mock_pool = AsyncMock()
    with patch("module_b_main._get_pool_or_503", return_value=mock_pool):
        with patch("ai.pipeline.run_pipeline", return_value={"status": "ok"}):
            response = client.post("/run-b", json={
                "type": "afternoon", "date": "2026-05-24",
                "batch_id": str(uuid.uuid4()),
            })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_pipeline_fallback_without_api_key():
    os.environ.pop("DEEPSEEK_API_KEY", None)
    from ai.pipeline import _has_api_key
    assert _has_api_key() is False


@pytest.mark.asyncio
async def test_mock_score_one():
    from ai.pipeline import _mock_score_one
    item = {"title": "GPT-5 released", "content": "OpenAI releases GPT-5"}
    score = _mock_score_one(item)
    assert 1 <= score <= 10
    # AI-related items should score higher
    low_item = {"title": "Weather report", "content": "Sunny today"}
    low_score = _mock_score_one(low_item)
    assert _mock_score_one(item) > low_score


@pytest.mark.asyncio
async def test_step_score_adds_metadata():
    from ai.pipeline import _step_score
    pool = AsyncMock()
    items = [
        {"id": "a", "title": "AI breakthrough", "content": "...", "source": "rss", "metadata": {}},
        {"id": "b", "title": "Weather report", "content": "...", "source": "rss", "metadata": {}},
    ]
    scored = await _step_score(pool, items)
    assert len(scored) == 2
    for item in scored:
        assert "ai_score" in item["metadata"]
        assert 1 <= item["metadata"]["ai_score"] <= 10


@pytest.mark.asyncio
async def test_step_filter_removes_low_scores():
    from ai.pipeline import _step_filter
    items = [
        {"id": "a", "metadata": {"ai_score": 9.0}},
        {"id": "b", "metadata": {"ai_score": 5.5}},
        {"id": "c", "metadata": {"ai_score": 6.0}},
    ]
    kept, removed = await _step_filter(items, threshold=6.0)
    kept_ids = [item["id"] for item in kept]
    assert "a" in kept_ids
    assert "c" in kept_ids
    assert "b" not in kept_ids
    assert len(removed) == 1


@pytest.mark.asyncio
async def test_step_dedup_heuristic():
    from ai.pipeline import _dedup_heuristic
    items = [
        {"id": "a", "title": "GPT-5 released by OpenAI", "source": "github"},
        {"id": "b", "title": "GPT-5 released by OpenAI — details", "source": "rss"},
        {"id": "c", "title": "Stock market update for May", "source": "rss"},
    ]
    kept, removed = _dedup_heuristic(items)
    kept_ids = [item["id"] for item in kept]
    assert "a" in kept_ids
    assert "c" in kept_ids
    # b should be removed as duplicate of a
    assert "b" not in kept_ids or removed > 0


@pytest.mark.asyncio
async def test_generate_mock_produces_valid_briefing():
    from ai.pipeline import _generate_mock
    items = [
        {"id": "a", "title": "AI breakthrough", "content": "Big AI news today",
         "summary": "Big news", "source": "github", "url": "https://example.com/1",
         "metadata": {"ai_score": 9.0}},
    ]
    briefing = _generate_mock(items, "morning", date.today())
    assert "tl_dr" in briefing
    assert "sections" in briefing
    assert "key_takeaways" in briefing
    assert isinstance(briefing["tl_dr"], list)


def test_extract_json_code_fence():
    from ai.pipeline import _extract_json
    import json
    raw = 'Some text ```json\n{"key": "value"}\n``` more'
    result = _extract_json(raw)
    assert json.loads(result) == {"key": "value"}


def test_extract_json_plain():
    from ai.pipeline import _extract_json
    import json
    result = _extract_json('{"status": "ok"}')
    assert json.loads(result) == {"status": "ok"}


def test_extract_json_returns_plain_on_failure():
    from ai.pipeline import _extract_json
    result = _extract_json("not json at all")
    assert isinstance(result, str)
