"""Tests for Module E — Scheduler & Dashboard."""
import importlib.util
import pytest
import sys, os
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

os.environ["SCHEDULE_ENABLED"] = "false"

_E_DIR = os.path.join(os.path.dirname(__file__), '..', 'module-e')
sys.path.insert(0, _E_DIR)
_spec = importlib.util.spec_from_file_location("module_e_main", os.path.join(_E_DIR, "main.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["module_e_main"] = _mod
_spec.loader.exec_module(_mod)

app = _mod.app
scheduled_trigger = _mod.scheduled_trigger

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "scheduler" in data


def test_schedule_status():
    response = client.get("/admin/schedule")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["morning_time"] == "08:00"


def test_trigger_returns_503_without_db():
    response = client.post("/admin/trigger?type=morning")
    assert response.status_code == 503


def test_trigger_invalid_type():
    response = client.post("/admin/trigger?type=midnight")
    assert response.status_code == 400


def test_overview_returns_503_without_db():
    response = client.get("/admin/overview")
    assert response.status_code == 503


def test_dashboard_stats_503():
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 503


def test_dashboard_logs_503():
    response = client.get("/api/dashboard/logs")
    assert response.status_code == 503


def test_dashboard_health_all_503():
    response = client.get("/api/dashboard/health/all")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_scheduled_trigger_logs_failure():
    with patch("module_e_main.execute_pipeline", side_effect=RuntimeError("boom")):
        await scheduled_trigger("morning")


def test_dashboard_get_pool_or_503():
    from dashboard.backend.dashboard import _get_pool_or_503
    with pytest.raises(HTTPException) as exc:
        _get_pool_or_503()
    assert exc.value.status_code == 503


# ── Pipeline tests ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_execute_pipeline_handles_a_down():
    from pipeline import execute_pipeline
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)
    mock_pool.fetchval = AsyncMock(return_value=0)
    mock_pool.execute = AsyncMock()

    with patch("pipeline.get_pool", return_value=mock_pool):
        with patch("pipeline.httpx.AsyncClient") as mock_client:
            client_inst = AsyncMock()
            resp = MagicMock()
            resp.raise_for_status.side_effect = Exception("Connection refused")
            client_inst.post.return_value = resp
            mock_client.return_value.__aenter__.return_value = client_inst
            result = await execute_pipeline("morning")
            assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_execute_pipeline_success_path():
    from pipeline import execute_pipeline
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)
    mock_pool.fetchval = AsyncMock(return_value=0)
    mock_pool.execute = AsyncMock()

    with patch("pipeline.get_pool", return_value=mock_pool):
        with patch("pipeline.httpx.AsyncClient") as mock_client:
            client_inst = AsyncMock()
            resp_a = MagicMock()
            resp_a.raise_for_status = MagicMock()
            resp_a.json.return_value = {"status": "ok", "fetched": 30}
            resp_b = MagicMock()
            resp_b.raise_for_status = MagicMock()
            resp_b.json.return_value = {"status": "ok", "briefing_id": "bf-123"}
            resp_c = MagicMock()
            resp_c.raise_for_status = MagicMock()
            resp_c.json.return_value = {"status": "ok", "pushed": 5}
            resp_d = MagicMock()
            resp_d.raise_for_status = MagicMock()
            resp_d.json.return_value = {"status": "ok", "results": []}
            client_inst.post.side_effect = [resp_a, resp_b, resp_c, resp_d]
            mock_client.return_value.__aenter__.return_value = client_inst
            result = await execute_pipeline("morning")
            assert result["status"] == "ok"
            assert result["briefing_id"] == "bf-123"
