"""test_weixin_oa.py — 微信公众号回调处理测试"""
import hashlib
import pytest
from unittest.mock import patch

from weixin_oa import (
    verify_signature,
    parse_xml_message,
    build_text_reply,
    build_news_reply,
    handle_message,
    _parse_tags,
)


# ── 签名验证 ─────────────────────────────────────────────────────


def test_verify_signature_correct():
    token = "test_token"
    timestamp = "1234567890"
    nonce = "abc"
    parts = sorted([token, timestamp, nonce])
    expected = hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()

    with patch("weixin_oa.settings") as mock_settings:
        mock_settings.WX_OA_TOKEN = token
        assert verify_signature(expected, timestamp, nonce) is True


def test_verify_signature_wrong():
    with patch("weixin_oa.settings") as mock_settings:
        mock_settings.WX_OA_TOKEN = "test_token"
        assert verify_signature("wrong_sig", "123", "abc") is False


def test_verify_signature_no_token():
    """未配置 token 时跳过验证"""
    with patch("weixin_oa.settings") as mock_settings:
        mock_settings.WX_OA_TOKEN = ""
        assert verify_signature("any", "123", "abc") is True


# ── XML 解析 ─────────────────────────────────────────────────────


def test_parse_text_message():
    xml = b"""<xml>
<ToUserName><![CDATA[gh_test]]></ToUserName>
<FromUserName><![CDATA[user_001]]></FromUserName>
<CreateTime>1234567890</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[hello]]></Content>
<MsgId>123456</MsgId>
</xml>"""

    msg = parse_xml_message(xml)
    assert msg["ToUserName"] == "gh_test"
    assert msg["FromUserName"] == "user_001"
    assert msg["MsgType"] == "text"
    assert msg["Content"] == "hello"
    assert msg["MsgId"] == 123456


def test_parse_subscribe_event():
    xml = b"""<xml>
<ToUserName><![CDATA[gh_test]]></ToUserName>
<FromUserName><![CDATA[user_002]]></FromUserName>
<CreateTime>1234567890</CreateTime>
<MsgType><![CDATA[event]]></MsgType>
<Event><![CDATA[subscribe]]></Event>
</xml>"""

    msg = parse_xml_message(xml)
    assert msg["MsgType"] == "event"
    assert msg["Event"] == "subscribe"


def test_parse_unsubscribe_event():
    xml = b"""<xml>
<ToUserName><![CDATA[gh_test]]></ToUserName>
<FromUserName><![CDATA[user_003]]></FromUserName>
<CreateTime>1234567890</CreateTime>
<MsgType><![CDATA[event]]></MsgType>
<Event><![CDATA[unsubscribe]]></Event>
</xml>"""

    msg = parse_xml_message(xml)
    assert msg["Event"] == "unsubscribe"


# ── 回复构建 ─────────────────────────────────────────────────────


def test_build_text_reply():
    reply = build_text_reply("user_001", "gh_test", "你好")
    assert "user_001" in reply
    assert "gh_test" in reply
    assert "你好" in reply
    assert "<MsgType><![CDATA[text]]></MsgType>" in reply


def test_build_news_reply():
    articles = [
        {"title": "标题1", "description": "描述1", "url": "http://a.com", "pic_url": "http://img.com/1.jpg"},
    ]
    reply = build_news_reply("user_001", "gh_test", articles)
    assert "标题1" in reply
    assert "ArticleCount>1" in reply
    assert "<MsgType><![CDATA[news]]></MsgType>" in reply


# ── 标签解析 ─────────────────────────────────────────────────────


def test_parse_tags_valid():
    result = _parse_tags("LLM 开源 Agent")
    assert result == ["LLM", "开源", "Agent"]


def test_parse_tags_with_chinese_separator():
    result = _parse_tags("LLM、开源、Agent")
    assert result == ["LLM", "开源", "Agent"]


def test_parse_tags_invalid():
    result = _parse_tags("不存在的标签")
    assert result == []


def test_parse_tags_mixed():
    result = _parse_tags("LLM 不存在 开源")
    assert result == ["LLM", "开源"]


# ── 消息处理（异步）───────────────────────────────────────────────


@pytest.mark.anyio
async def test_handle_subscribe_event():
    msg = {
        "MsgType": "event",
        "Event": "subscribe",
        "FromUserName": "user_new",
        "ToUserName": "gh_test",
    }
    reply = await handle_message(msg)
    assert reply is not None
    assert "欢迎" in reply
    assert "订阅" in reply


@pytest.mark.anyio
async def test_handle_unsubscribe_event():
    msg = {
        "MsgType": "event",
        "Event": "unsubscribe",
        "FromUserName": "user_leave",
        "ToUserName": "gh_test",
    }
    reply = await handle_message(msg)
    assert reply is None


@pytest.mark.anyio
async def test_handle_text_subscribe():
    msg = {
        "MsgType": "text",
        "Content": "订阅",
        "FromUserName": "user_001",
        "ToUserName": "gh_test",
    }
    reply = await handle_message(msg)
    assert reply is not None
    assert "LLM" in reply
    assert "可选标签" in reply


@pytest.mark.anyio
async def test_handle_text_preferences():
    msg = {
        "MsgType": "text",
        "Content": "偏好",
        "FromUserName": "user_001",
        "ToUserName": "gh_test",
    }
    reply = await handle_message(msg)
    assert reply is not None
    assert "preferences.html" in reply


@pytest.mark.anyio
async def test_handle_text_subscribe_tags():
    msg = {
        "MsgType": "text",
        "Content": "订阅 LLM 开源 Agent",
        "FromUserName": "user_001",
        "ToUserName": "gh_test",
    }
    reply = await handle_message(msg)
    assert reply is not None
    assert "已订阅标签" in reply
    assert "LLM" in reply


@pytest.mark.anyio
async def test_handle_text_subscribe_invalid_tags():
    msg = {
        "MsgType": "text",
        "Content": "订阅 不存在的标签",
        "FromUserName": "user_001",
        "ToUserName": "gh_test",
    }
    reply = await handle_message(msg)
    assert reply is not None
    assert "未识别" in reply


@pytest.mark.anyio
async def test_handle_text_unknown():
    msg = {
        "MsgType": "text",
        "Content": "随便说点什么",
        "FromUserName": "user_001",
        "ToUserName": "gh_test",
    }
    reply = await handle_message(msg)
    assert reply is not None
    assert "订阅" in reply


@pytest.mark.anyio
async def test_handle_image_message():
    """非文字非事件消息应返回 None"""
    msg = {
        "MsgType": "image",
        "FromUserName": "user_001",
        "ToUserName": "gh_test",
    }
    reply = await handle_message(msg)
    assert reply is None
