"""test_main.py — 所有 /api 路由测试"""
import pytest


BRIEFING_ID_MORNING = "b0000001-0000-0000-0000-000000000001"


@pytest.mark.anyio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.anyio
async def test_latest_briefing_morning(client):
    resp = await client.get("/api/briefings/latest?type=morning")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "morning"
    assert isinstance(data["tl_dr"], list)
    assert len(data["tl_dr"]) > 0


@pytest.mark.anyio
async def test_latest_briefing_evening(client):
    resp = await client.get("/api/briefings/latest?type=evening")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "evening"


@pytest.mark.anyio
async def test_latest_briefing_missing_type(client):
    resp = await client.get("/api/briefings/latest")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_latest_briefing_bad_type(client):
    resp = await client.get("/api/briefings/latest?type=afternoon")
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_history_default(client):
    resp = await client.get("/api/briefings/history")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data


@pytest.mark.anyio
async def test_history_with_keyword(client):
    resp = await client.get("/api/briefings/history?keyword=DeepSeek")
    assert resp.status_code == 200
    data = resp.json()
    # seed_data 中有 DeepSeek 相关简报
    assert data["total"] >= 1


@pytest.mark.anyio
async def test_history_with_keyword_no_match(client):
    resp = await client.get("/api/briefings/history?keyword=xyz123nonexistent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


@pytest.mark.anyio
async def test_briefing_detail_found(client):
    resp = await client.get(f"/api/briefings/{BRIEFING_ID_MORNING}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == BRIEFING_ID_MORNING
    assert isinstance(data["sections"], list)
    assert isinstance(data["key_takeaways"], list)


@pytest.mark.anyio
async def test_briefing_detail_not_found(client):
    resp = await client.get("/api/briefings/00000000-0000-0000-0000-000000000099")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_briefing_detail_invalid_uuid(client):
    resp = await client.get("/api/briefings/not-a-uuid")
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_subscribe(client):
    resp = await client.post("/api/subscribe", json={
        "openid": "test_openid_001",
        "morning_enabled": True,
        "evening_enabled": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.anyio
async def test_unsubscribe(client):
    resp = await client.post("/api/unsubscribe", json={
        "openid": "test_openid_001",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.anyio
async def test_push_dry_run(client):
    """无微信配置时应返回 dry_run"""
    resp = await client.post("/push", json={
        "briefing_id": BRIEFING_ID_MORNING,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "dry_run"


@pytest.mark.anyio
async def test_push_briefing_not_found(client):
    resp = await client.post("/push", json={
        "briefing_id": "00000000-0000-0000-0000-000000000099",
    })
    assert resp.status_code == 404
