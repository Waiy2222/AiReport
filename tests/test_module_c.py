"""Tests for Module C — WeChat Mini Program Backend API."""
import importlib.util
import pytest
import sys, os
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

_C_DIR = os.path.join(os.path.dirname(__file__), '..', 'module-c', 'backend')
sys.path.insert(0, _C_DIR)
_spec = importlib.util.spec_from_file_location("module_c_main", os.path.join(_C_DIR, "main.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["module_c_main"] = _mod
_spec.loader.exec_module(_mod)

app = _mod.app
_get_pool_or_503 = _mod._get_pool_or_503

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_pool_or_503():
    with pytest.raises(HTTPException) as exc:
        _get_pool_or_503()
    assert exc.value.status_code == 503


def test_latest_briefing_returns_503_without_db():
    response = client.get("/api/briefings/latest?type=morning")
    assert response.status_code == 503


def test_history_returns_503_without_db():
    response = client.get("/api/briefings/history")
    assert response.status_code == 503


def test_push_valid_type():
    response = client.post("/push", json={"type": "morning"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_push_invalid_type():
    response = client.post("/push", json={"type": "midnight"})
    assert response.status_code == 400


def test_latest_briefing_returns_data():
    from datetime import datetime, timezone
    mock_pool = AsyncMock()
    ts = datetime(2026, 5, 24, 8, 0, 0, tzinfo=timezone.utc)
    mock_row = MagicMock()
    mock_row.__getitem__.side_effect = lambda k: {
        "id": "b0000001-0000-0000-0000-000000000001",
        "type": "morning",
        "date": "2026-05-24",
        "tl_dr": ["point 1"],
        "sections": [],
        "key_takeaways": ["takeaway 1"],
        "generated_at": ts,
    }.get(k)
    mock_pool.fetchrow = AsyncMock(return_value=mock_row)
    with patch("module_c_main._get_pool_or_503", return_value=mock_pool):
        response = client.get("/api/briefings/latest?type=morning")
        assert response.status_code == 200
        assert response.json()["id"] == "b0000001-0000-0000-0000-000000000001"


def test_latest_briefing_404_when_none():
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)
    with patch("module_c_main._get_pool_or_503", return_value=mock_pool):
        response = client.get("/api/briefings/latest?type=morning")
        assert response.status_code == 404


def test_latest_briefing_invalid_type():
    mock_pool = AsyncMock()
    with patch("module_c_main._get_pool_or_503", return_value=mock_pool):
        response = client.get("/api/briefings/latest?type=invalid")
        assert response.status_code == 400


def test_history_paginated():
    from datetime import datetime, timezone
    mock_pool = AsyncMock()
    ts = datetime(2026, 5, 24, 8, 0, 0, tzinfo=timezone.utc)
    mock_row = MagicMock()
    mock_row.__getitem__.side_effect = lambda k: {
        "id": "b001", "type": "morning", "date": "2026-05-24",
        "tl_dr": ["p1"], "generated_at": ts,
    }.get(k)
    mock_pool.fetch = AsyncMock(return_value=[mock_row])
    mock_pool.fetchval = AsyncMock(return_value=10)
    with patch("module_c_main._get_pool_or_503", return_value=mock_pool):
        response = client.get("/api/briefings/history?page=1&size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert len(data["items"]) == 1


def test_subscribe():
    mock_pool = AsyncMock()
    with patch("module_c_main._get_pool_or_503", return_value=mock_pool):
        response = client.post("/api/subscribe", json={
            "openid": "test_user_001",
            "morning_enabled": True, "evening_enabled": False,
        })
        assert response.status_code == 200
        mock_pool.execute.assert_called_once()


def test_unsubscribe():
    mock_pool = AsyncMock()
    with patch("module_c_main._get_pool_or_503", return_value=mock_pool):
        response = client.post("/api/unsubscribe", json={"openid": "test_user_001"})
        assert response.status_code == 200
        mock_pool.execute.assert_called_once()
