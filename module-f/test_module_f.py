"""TDD: module-f/main.py — 视频生成模块测试"""
import sys
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

# 确保 module-f/main.py 被正确导入
sys.path.insert(0, "module-f")


@pytest.fixture
def app():
    """导入 app，mock 掉 pipeline 初始化"""
    mock_pipeline = MagicMock()
    mock_pipeline.status = AsyncMock(return_value={
        "video_id": "test-id",
        "status": "done",
        "title": "Test Video",
        "output_path": "/output/test.mp4",
        "duration_seconds": 120,
        "error_msg": None,
        "metadata": {},
    })
    mock_pipeline.list_videos = AsyncMock(return_value=[])
    mock_pipeline.start = AsyncMock(return_value={
        "id": "test-id",
        "status": "processing",
        "type": "ai_agent_weekly",
        "date": "2026-06-05",
    })

    import main
    main.pipeline = mock_pipeline
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
    assert resp.json()["status"] == "ok"


# ── 生成视频 ──────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_generate_default(client):
    """POST /generate 默认参数 → 200"""
    resp = await client.post("/generate", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processing"
    assert "video_id" in data
    assert "message" in data


@pytest.mark.anyio(asyncio_mode="auto")
async def test_generate_with_type(client):
    """POST /generate 指定类型 → 200"""
    resp = await client.post("/generate", json={"type": "ai_agent_weekly"})
    assert resp.status_code == 200


@pytest.mark.anyio(asyncio_mode="auto")
async def test_generate_with_date(client):
    """POST /generate 指定日期 → 200"""
    resp = await client.post("/generate", json={"type": "ai_agent_weekly", "date": "2026-06-01"})
    assert resp.status_code == 200


@pytest.mark.anyio(asyncio_mode="auto")
async def test_generate_no_pipeline(client):
    """POST /generate pipeline 未初始化 → 503"""
    import main
    old = main.pipeline
    main.pipeline = None
    resp = await client.post("/generate", json={})
    main.pipeline = old
    assert resp.status_code == 503


# ── 查询状态 ──────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_status_found(client):
    """GET /status/{id} → 200"""
    resp = await client.get("/status/test-id")
    assert resp.status_code == 200
    data = resp.json()
    assert data["video_id"] == "test-id"
    assert data["status"] == "done"


@pytest.mark.anyio(asyncio_mode="auto")
async def test_status_not_found(client):
    """GET /status/{id} 不存在 → 404"""
    import main
    old = main.pipeline
    mock_p = MagicMock()
    mock_p.status = AsyncMock(side_effect=ValueError("not found"))
    main.pipeline = mock_p
    resp = await client.get("/status/nonexistent")
    main.pipeline = old
    assert resp.status_code == 404


# ── 视频列表 ──────────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_list_videos(client):
    """GET /videos → 200"""
    resp = await client.get("/videos")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.anyio(asyncio_mode="auto")
async def test_list_videos_with_params(client):
    """GET /videos?limit=5&offset=10 → 200"""
    resp = await client.get("/videos", params={"limit": 5, "offset": 10})
    assert resp.status_code == 200


@pytest.mark.anyio(asyncio_mode="auto")
async def test_list_videos_no_pipeline(client):
    """GET /videos pipeline 未初始化 → 503"""
    import main
    old = main.pipeline
    main.pipeline = None
    resp = await client.get("/videos")
    main.pipeline = old
    assert resp.status_code == 503
