"""微信公众号消息回调处理（Phase 2 新增）

处理微信服务器推送的用户消息事件：
- 关注/取关
- 文字消息（订阅、偏好设置）
- 菜单点击

关键约束：微信回调 5 秒超时，收到消息立即返回空响应，异步处理。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

# 预置标签列表（与 schema_v2.sql / mock_data.py 一致）
AVAILABLE_TAGS = [
    "LLM", "开源", "Python", "AI安全", "Agent",
    "AI产品", "RAG", "多模态", "AI编程", "AI政策", "融资", "基础设施",
]

# ── 签名验证 ─────────────────────────────────────────────────────


def verify_signature(signature: str, timestamp: str, nonce: str) -> bool:
    """验证微信服务器签名（SHA1）"""
    token = settings.WX_OA_TOKEN
    if not token:
        logger.warning("WX_OA_TOKEN not configured, skipping verification")
        return True

    parts = sorted([token, timestamp, nonce])
    digest = hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()
    return digest == signature


# ── XML 解析 ─────────────────────────────────────────────────────


def parse_xml_message(xml_bytes: bytes) -> dict[str, Any]:
    """解析微信推送的 XML 消息为字典"""
    root = ET.fromstring(xml_bytes)
    msg = {}
    for child in root:
        tag = child.tag
        if tag in ("CreateTime", "MsgId", "PicCount", "Latitude", "Longitude", "Scale"):
            try:
                msg[tag] = int(child.text or 0)
            except (ValueError, TypeError):
                msg[tag] = child.text
        else:
            msg[tag] = (child.text or "").strip()
    return msg


# ── 回复构建 ─────────────────────────────────────────────────────


def build_text_reply(from_user: str, to_user: str, content: str) -> str:
    """构建文本消息 XML 回复"""
    return f"""<xml>
<ToUserName><![CDATA[{from_user}]]></ToUserName>
<FromUserName><![CDATA[{to_user}]]></FromUserName>
<CreateTime>{int(__import__('time').time())}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>"""


def build_news_reply(from_user: str, to_user: str, articles: list[dict]) -> str:
    """构建图文消息 XML 回复

    articles: [{"title": "...", "description": "...", "url": "...", "pic_url": "..."}]
    """
    items_xml = ""
    for a in articles:
        items_xml += f"""<item>
<Title><![CDATA[{a.get('title', '')}]]></Title>
<Description><![CDATA[{a.get('description', '')}]]></Description>
<PicUrl><![CDATA[{a.get('pic_url', '')}]]></PicUrl>
<Url><![CDATA[{a.get('url', '')}]]></Url>
</item>"""

    return f"""<xml>
<ToUserName><![CDATA[{from_user}]]></ToUserName>
<FromUserName><![CDATA[{to_user}]]></FromUserName>
<CreateTime>{int(__import__('time').time())}</CreateTime>
<MsgType><![CDATA[news]]></MsgType>
<ArticleCount>{len(articles)}</ArticleCount>
<Articles>{items_xml}</Articles>
</xml>"""


# ── 消息处理 ─────────────────────────────────────────────────────


async def handle_message(msg: dict, db_pool=None) -> str | None:
    """处理用户消息，返回回复 XML（或 None 不回复）

    异步处理逻辑：
    - 关注事件 → 自动回复引导文字
    - 取关事件 → 更新订阅状态
    - 文字消息 → 解析命令（订阅/偏好/其他）
    """
    msg_type = msg.get("MsgType", "")
    from_user = msg.get("FromUserName", "")
    to_user = msg.get("ToUserName", "")

    # 事件消息
    if msg_type == "event":
        event = msg.get("Event", "").lower()

        if event == "subscribe":
            # 新关注 → 异步处理，立即返回欢迎消息
            asyncio.create_task(_on_subscribe(from_user, db_pool))
            return build_text_reply(
                from_user, to_user,
                "欢迎关注 AI 资讯早报/晚报！\n\n"
                "回复「订阅」查看可选标签\n"
                "回复「偏好」打开标签设置页面\n"
                "回复「订阅 LLM 开源 Agent」直接订阅标签",
            )

        if event == "unsubscribe":
            asyncio.create_task(_on_unsubscribe(from_user, db_pool))
            return None  # 取关不回复

    # 文字消息
    if msg_type == "text":
        content = msg.get("Content", "").strip()

        # 回复「订阅」→ 返回标签列表
        if content == "订阅":
            return _build_tag_list_reply(from_user, to_user)

        # 回复「偏好」→ 返回 H5 链接
        if content == "偏好":
            h5_url = f"{settings.H5_BASE_URL}/preferences.html?openid={from_user}"
            return build_text_reply(
                from_user, to_user,
                f"点击设置偏好：\n{h5_url}",
            )

        # 回复「订阅 标签1 标签2 ...」→ 解析标签
        match = re.match(r"^订阅\s+(.+)$", content)
        if match:
            tags_str = match.group(1)
            parsed = _parse_tags(tags_str)
            if parsed:
                asyncio.create_task(_save_user_tags(from_user, parsed, db_pool))
                return build_text_reply(
                    from_user, to_user,
                    f"已订阅标签：{', '.join(parsed)}\n"
                    f"后续将根据你的偏好推送个性化内容。",
                )
            else:
                return build_text_reply(
                    from_user, to_user,
                    "未识别到有效标签。回复「订阅」查看可选标签列表。",
                )

        # 其他文字 → 引导
        return build_text_reply(
            from_user, to_user,
            "回复「订阅」查看可选标签\n"
            "回复「偏好」打开标签设置页面\n"
            "回复「订阅 LLM 开源 Agent」直接订阅标签",
        )

    return None


# ── 内部辅助 ─────────────────────────────────────────────────────


def _build_tag_list_reply(from_user: str, to_user: str) -> str:
    """构建标签列表回复"""
    tag_lines = " / ".join(AVAILABLE_TAGS)
    return build_text_reply(
        from_user, to_user,
        f"可选标签：\n{tag_lines}\n\n"
        "回复「订阅 标签1 标签2」订阅，如：\n"
        "订阅 LLM 开源 Agent",
    )


def _parse_tags(text: str) -> list[str]:
    """从用户输入中解析标签，只保留已知标签"""
    # 支持空格和中文顿号分隔
    parts = re.split(r"[、\s]+", text.strip())
    valid = [t for t in parts if t in AVAILABLE_TAGS]
    return valid


async def _on_subscribe(openid: str, db_pool=None) -> None:
    """异步处理关注事件 — 记录到数据库"""
    try:
        if db_pool:
            await db_pool.execute(
                """INSERT INTO subscriptions (openid, subscribed, preferences)
                   VALUES ($1, true, '{"tags":[]}')
                   ON CONFLICT (openid) DO UPDATE SET subscribed=true""",
                openid,
            )
            logger.info("User %s subscribed", openid)
    except Exception:
        logger.warning("Failed to record subscribe for %s", openid, exc_info=True)


async def _on_unsubscribe(openid: str, db_pool=None) -> None:
    """异步处理取关事件 — 更新数据库"""
    try:
        if db_pool:
            await db_pool.execute(
                "UPDATE subscriptions SET subscribed=false WHERE openid=$1",
                openid,
            )
            logger.info("User %s unsubscribed", openid)
    except Exception:
        logger.warning("Failed to record unsubscribe for %s", openid, exc_info=True)


async def _save_user_tags(openid: str, tags: list[str], db_pool=None) -> None:
    """异步保存用户标签偏好"""
    import json
    try:
        if db_pool:
            await db_pool.execute(
                """INSERT INTO subscriptions (openid, subscribed, preferences)
                   VALUES ($1, true, $2)
                   ON CONFLICT (openid) DO UPDATE SET
                     preferences = $2, subscribed = true""",
                openid, json.dumps({"tags": tags}),
            )
            logger.info("User %s tags updated: %s", openid, tags)
    except Exception:
        logger.warning("Failed to save tags for %s", openid, exc_info=True)
