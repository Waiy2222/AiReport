"""test_tags.py — 标签管理 + 用户行为 + 用户画像 API 测试"""
import pytest


@pytest.mark.anyio
async def test_list_tags(client):
    """GET /api/tags 返回标签列表"""
    resp = await client.get("/api/tags")
    assert resp.status_code == 200
    data = resp.json()
    assert "tags" in data
    assert len(data["tags"]) > 0
    # 检查标签结构
    tag = data["tags"][0]
    assert "tag" in tag
    assert "label_zh" in tag


@pytest.mark.anyio
async def test_list_tags_contains_expected(client):
    """标签列表包含预期标签"""
    resp = await client.get("/api/tags")
    tags = [t["tag"] for t in resp.json()["tags"]]
    assert "LLM" in tags
    assert "开源" in tags
    assert "Agent" in tags


@pytest.mark.anyio
async def test_set_preferences(client):
    """POST /api/user/preferences 设置偏好"""
    resp = await client.post("/api/user/preferences", json={
        "openid": "test_user_001",
        "tags": ["LLM", "开源", "Agent"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["openid"] == "test_user_001"
    assert data["tags"] == ["LLM", "开源", "Agent"]


@pytest.mark.anyio
async def test_get_preferences(client):
    """GET /api/user/preferences 获取偏好"""
    # 先设置
    await client.post("/api/user/preferences", json={
        "openid": "test_user_002",
        "tags": ["Python", "AI编程"],
    })
    # 再获取
    resp = await client.get("/api/user/preferences?openid=test_user_002")
    assert resp.status_code == 200
    data = resp.json()
    assert "Python" in data["tags"]


@pytest.mark.anyio
async def test_get_preferences_unknown_user(client):
    """未知用户返回空标签"""
    resp = await client.get("/api/user/preferences?openid=unknown_user_999")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tags"] == []


@pytest.mark.anyio
async def test_get_user_profile(client):
    """GET /api/user/{openid}/profile 返回用户画像"""
    resp = await client.get("/api/user/mock_openid_user_001/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["openid"] == "mock_openid_user_001"
    assert "tags" in data
    assert "recent_clicks" in data
    assert "weight_map" in data


@pytest.mark.anyio
async def test_get_user_profile_has_tags(client):
    """mock 用户有标签"""
    resp = await client.get("/api/user/mock_openid_user_001/profile")
    data = resp.json()
    assert len(data["tags"]) > 0
    assert "LLM" in data["tags"]


@pytest.mark.anyio
async def test_get_user_profile_has_clicks(client):
    """mock 用户有点击记录"""
    resp = await client.get("/api/user/mock_openid_user_001/profile")
    data = resp.json()
    assert len(data["recent_clicks"]) > 0
    click = data["recent_clicks"][0]
    assert "item_title" in click
    assert "action" in click


@pytest.mark.anyio
async def test_report_behavior_click(client):
    """POST /api/behavior 上报点击行为"""
    resp = await client.post("/api/behavior", json={
        "openid": "test_user_001",
        "briefing_id": "b0000001-0000-0000-0000-000000000001",
        "action": "click",
        "item_index": 0,
        "item_title": "测试标题",
        "item_url": "https://example.com",
        "item_tags": ["LLM", "测试"],
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_report_behavior_invalid_action(client):
    """无效 action 应返回 400"""
    resp = await client.post("/api/behavior", json={
        "openid": "test_user_001",
        "briefing_id": "b0000001-0000-0000-0000-000000000001",
        "action": "invalid_action",
    })
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_report_behavior_view(client):
    """上报 view 行为"""
    resp = await client.post("/api/behavior", json={
        "openid": "test_user_001",
        "briefing_id": "b0000001-0000-0000-0000-000000000001",
        "action": "view",
    })
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_report_behavior_share(client):
    """上报 share 行为"""
    resp = await client.post("/api/behavior", json={
        "openid": "test_user_001",
        "briefing_id": "b0000001-0000-0000-0000-000000000001",
        "action": "share",
        "item_tags": ["LLM"],
    })
    assert resp.status_code == 200
