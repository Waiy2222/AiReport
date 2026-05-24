"""test_push.py — 订阅消息推送测试"""
import pytest
from unittest.mock import AsyncMock, patch

from push import get_access_token, send_subscribe_message, batch_push


@pytest.mark.anyio
async def test_get_access_token_cached():
    mock_resp = AsyncMock()
    mock_resp.json.return_value = {
        "access_token": "mock_token_123",
        "expires_in": 7200,
    }

    # 清缓存
    import push
    push._token_cache = {"value": None, "expires_at": 0}

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        token = await get_access_token()
        assert token == "mock_token_123"
        # 第二次调用应使用缓存（不再次请求 HTTP）
        token2 = await get_access_token()
        assert token2 == "mock_token_123"


@pytest.mark.anyio
async def test_get_access_token_wechat_error():
    mock_resp = AsyncMock()
    mock_resp.json.return_value = {
        "errcode": 40001,
        "errmsg": "invalid credential",
    }

    import push
    push._token_cache = {"value": None, "expires_at": 0}

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="获取 access_token 失败"):
            await get_access_token()


@pytest.mark.anyio
async def test_send_subscribe_message():
    mock_resp = AsyncMock()
    mock_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

    briefing = {
        "id": "b0000001-0000-0000-0000-000000000001",
        "type": "morning",
        "date": "2026-05-24",
        "tl_dr": ["AI资讯要点标题"],
    }

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        result = await send_subscribe_message("openid_001", briefing, "fake_token")
        assert result["result"] == "success"
        assert result["openid"] == "openid_001"


@pytest.mark.anyio
async def test_batch_push_all_success():
    mock_token_resp = AsyncMock()
    mock_token_resp.json.return_value = {
        "access_token": "mock_token",
        "expires_in": 7200,
    }
    mock_send_resp = AsyncMock()
    mock_send_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

    import push
    push._token_cache = {"value": None, "expires_at": 0}

    briefing = {
        "id": "b0000001-0000-0000-0000-000000000001",
        "type": "morning",
        "date": "2026-05-24",
        "tl_dr": ["要点1", "要点2"],
    }
    targets = [
        {"openid": "u1", "morning_enabled": True, "evening_enabled": True},
        {"openid": "u2", "morning_enabled": True, "evening_enabled": False},
    ]

    with patch("httpx.AsyncClient.get", return_value=mock_token_resp), \
         patch("httpx.AsyncClient.post", return_value=mock_send_resp):
        result = await batch_push(briefing, targets)
        assert result["total"] == 2
        assert result["success"] == 2
        assert result["failed"] == 0


@pytest.mark.anyio
async def test_batch_push_partial_failure():
    """两次发送，token请求成功 + 第一次成功 + 第二次失败"""
    mock_token_resp = AsyncMock()
    mock_token_resp.json.return_value = {
        "access_token": "mock_token",
        "expires_in": 7200,
    }

    import push
    push._token_cache = {"value": None, "expires_at": 0}

    briefing = {
        "id": "b0000001-0000-0000-0000-000000000001",
        "type": "morning",
        "date": "2026-05-24",
        "tl_dr": ["要点"],
    }
    targets = [
        {"openid": "u1", "morning_enabled": True, "evening_enabled": True},
        {"openid": "u2", "morning_enabled": True, "evening_enabled": False},
    ]

    # 用 side_effect 模拟一次成功一次失败
    call_count = [0]

    async def mock_post(url, json, timeout):
        call_count[0] += 1
        mock = AsyncMock()
        if call_count[0] == 1:
            mock.json.return_value = {"errcode": 0, "errmsg": "ok"}
        else:
            mock.json.return_value = {"errcode": 40003, "errmsg": "invalid openid"}
        return mock

    with patch("httpx.AsyncClient.get", return_value=mock_token_resp), \
         patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await batch_push(briefing, targets)
        assert result["total"] == 2
        assert result["success"] == 1
        assert result["failed"] == 1
