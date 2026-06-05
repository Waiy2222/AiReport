"""TDD: module-e/main.py — 调度管理与 Dashboard 测试"""
import sys
import importlib
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

# 确保 module-e/main.py 被正确导入
sys.path.insert(0, "module-e")


@pytest.fixture
def app():
    """导入 app，mock 掉数据库初始化和调度器"""
    with patch("main.init_db", new_callable=AsyncMock):
        with patch("main.close_db", new_callable=AsyncMock):
            import main
            main.SCHEDULE_ENABLED = False
            yield main.app


@pytest.fixture
async def client(app):
    """异步测试客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── 健康检查 ──────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_health(client):
    """GET /health → 200"""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "db" in data
    assert "scheduler" in data


# ── 调度状态 ──────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_schedule_status(client):
    """GET /admin/schedule → 返回调度配置"""
    resp = await client.get("/admin/schedule")
    assert resp.status_code == 200
    data = resp.json()
    assert "scheduler_running" in data
    assert "enabled" in data
    assert "morning_time" in data
    assert "evening_time" in data
    assert "timezone" in data


# ── 触发全链路 ────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_trigger_invalid_type(client):
    """POST /admin/trigger?type=invalid → 400"""
    resp = await client.post("/admin/trigger", params={"type": "invalid"})
    assert resp.status_code == 400


@pytest.mark.anyio(asyncio_mode="auto")
async def test_trigger_no_db(client):
    """POST /admin/trigger 无 DB → 503"""
    with patch("main.get_pool", side_effect=RuntimeError("no pool")):
        resp = await client.post("/admin/trigger", params={"type": "morning"})
    assert resp.status_code == 503


@pytest.mark.anyio(asyncio_mode="auto")
async def test_trigger_success(client):
    """POST /admin/trigger 正常执行 → 200"""
    mock_pool = AsyncMock()
    mock_pool.fetchval = AsyncMock(return_value=1)

    with patch("main.get_pool", return_value=mock_pool):
        with patch("main.execute_pipeline", new_callable=AsyncMock,
                   return_value={"status": "ok", "batch_id": "test"}):
            resp = await client.post("/admin/trigger", params={"type": "morning"})

    assert resp.status_code == 200


# ── 运行总览 ──────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_overview_no_db(client):
    """GET /admin/overview 无 DB → 503"""
    with patch("main.get_pool", side_effect=RuntimeError("no pool")):
        resp = await client.get("/admin/overview")
    assert resp.status_code == 503


# ── 视频触发 ──────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_trigger_video_no_db(client):
    """POST /admin/trigger-video 无 DB → 503"""
    with patch("main.get_pool", side_effect=RuntimeError("no pool")):
        resp = await client.post("/admin/trigger-video", params={"type": "ai_agent_weekly"})
    assert resp.status_code == 503


# ── 配置常量 ──────────────────────────────────────────────────────────

def test_schedule_config():
    """调度配置有默认值"""
    import main
    assert hasattr(main, "MORNING_TIME")
    assert hasattr(main, "EVENING_TIME")
    assert hasattr(main, "SCHEDULE_ENABLED")
