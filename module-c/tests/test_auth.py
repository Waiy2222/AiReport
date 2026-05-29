"""test_auth.py — 微信登录验证测试"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from auth import code_to_openid, verify_token


@pytest.mark.anyio
async def test_code_to_openid_valid():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "openid": "mock_openid_abc123",
        "session_key": "mock_session_key",
    }

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        result = await code_to_openid("valid_code")
        assert result == "mock_openid_abc123"


@pytest.mark.anyio
async def test_code_to_openid_invalid():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "errcode": 40029,
        "errmsg": "invalid code",
    }

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        result = await code_to_openid("bad_code")
        assert result is None


def test_verify_token_missing():
    assert verify_token(None) is None


def test_verify_token_empty():
    assert verify_token("") is None


def test_verify_token_valid():
    result = verify_token("Bearer mock_openid_user_001")
    assert result == "mock_openid_user_001"
