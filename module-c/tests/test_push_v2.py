"""test_push_v2.py — Phase 2 个性化推送测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from push import filter_briefing_by_tags, batch_push


# ── 标签过滤逻辑 ─────────────────────────────────────────────────


def test_filter_by_tags_matching():
    """有标签用户应只收到匹配标签的内容"""
    briefing = {
        "id": "b001",
        "type": "morning",
        "sections": [
            {
                "title": "大模型",
                "items": [
                    {"title": "LLM新闻", "tags": ["LLM", "开源"]},
                    {"title": "Agent新闻", "tags": ["Agent"]},
                    {"title": "政策新闻", "tags": ["AI政策"]},
                ],
            },
        ],
    }

    result = filter_briefing_by_tags(briefing, ["LLM", "开源"])
    assert len(result["sections"]) == 1
    assert len(result["sections"][0]["items"]) == 1
    assert result["sections"][0]["items"][0]["title"] == "LLM新闻"


def test_filter_by_tags_multiple_sections():
    """跨 section 匹配"""
    briefing = {
        "id": "b001",
        "sections": [
            {
                "title": "大模型",
                "items": [
                    {"title": "LLM新闻", "tags": ["LLM"]},
                ],
            },
            {
                "title": "Agent",
                "items": [
                    {"title": "Agent新闻", "tags": ["Agent"]},
                ],
            },
            {
                "title": "政策",
                "items": [
                    {"title": "政策新闻", "tags": ["AI政策"]},
                ],
            },
        ],
    }

    result = filter_briefing_by_tags(briefing, ["LLM", "Agent"])
    assert len(result["sections"]) == 2


def test_filter_by_tags_no_match_fallback():
    """无匹配时返回完整简报（兜底）"""
    briefing = {
        "id": "b001",
        "sections": [
            {
                "title": "大模型",
                "items": [
                    {"title": "LLM新闻", "tags": ["LLM"]},
                ],
            },
        ],
    }

    result = filter_briefing_by_tags(briefing, ["融资"])
    # 兜底：返回完整简报
    assert len(result["sections"]) == 1
    assert len(result["sections"][0]["items"]) == 1


def test_filter_by_tags_empty_user_tags():
    """无标签用户（冷启动）返回完整简报"""
    briefing = {
        "id": "b001",
        "sections": [
            {
                "title": "大模型",
                "items": [
                    {"title": "LLM新闻", "tags": ["LLM"]},
                    {"title": "Agent新闻", "tags": ["Agent"]},
                ],
            },
        ],
    }

    result = filter_briefing_by_tags(briefing, [])
    assert len(result["sections"][0]["items"]) == 2


def test_filter_preserves_briefing_structure():
    """过滤后保留简报基本结构"""
    briefing = {
        "id": "b001",
        "type": "morning",
        "date": "2026-05-28",
        "tl_dr": ["要点1"],
        "sections": [
            {
                "title": "大模型",
                "items": [
                    {"title": "LLM新闻", "tags": ["LLM"]},
                ],
            },
        ],
        "key_takeaways": ["洞察1"],
    }

    result = filter_briefing_by_tags(briefing, ["LLM"])
    assert result["id"] == "b001"
    assert result["type"] == "morning"
    assert result["tl_dr"] == ["要点1"]
    assert result["key_takeaways"] == ["洞察1"]


# ── 个性化推送流程 ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_batch_push_with_personalization():
    """有标签用户推送时应调用过滤"""
    mock_token_resp = MagicMock()
    mock_token_resp.json.return_value = {
        "access_token": "mock_token",
        "expires_in": 7200,
    }
    mock_send_resp = MagicMock()
    mock_send_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

    import push
    push._token_cache = {"value": None, "expires_at": 0}

    briefing = {
        "id": "b001",
        "type": "morning",
        "date": "2026-05-28",
        "tl_dr": ["要点"],
        "sections": [
            {
                "title": "大模型",
                "items": [
                    {"title": "LLM新闻", "tags": ["LLM"]},
                    {"title": "Agent新闻", "tags": ["Agent"]},
                ],
            },
        ],
    }

    targets = [
        {"openid": "u1", "tags": ["LLM"]},
        {"openid": "u2", "tags": []},
    ]

    async def mock_get(*args, **kwargs):
        return mock_token_resp

    async def mock_post(*args, **kwargs):
        return mock_send_resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get), \
         patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await batch_push(briefing, targets)
        assert result["total"] == 2
        assert result["success"] == 2
        assert result["personalized"] == 1
        assert result["default_fallback"] == 1


@pytest.mark.anyio
async def test_push_dry_run_with_type(client):
    """POST /push 带 type 参数（dry_run 模式）"""
    resp = await client.post("/push", json={
        "type": "morning",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "dry_run"


@pytest.mark.anyio
async def test_push_dry_run_with_briefing_id(client):
    """POST /push 带 briefing_id（dry_run 模式）"""
    resp = await client.post("/push", json={
        "briefing_id": "b0000001-0000-0000-0000-000000000001",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "dry_run"


@pytest.mark.anyio
async def test_push_no_params(client):
    """POST /push 无参数应返回 400"""
    resp = await client.post("/push", json={})
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_push_type_not_found(client):
    """POST /push type 不存在应返回 404"""
    resp = await client.post("/push", json={"type": "afternoon"})
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_push_dry_run_has_personalized_fields(client):
    """dry_run 返回包含个性化推送字段"""
    resp = await client.post("/push", json={"type": "morning"})
    data = resp.json()
    assert "personalized" in data
    assert "default_fallback" in data
