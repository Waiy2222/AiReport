"""微信公众号发布 — 素材上传 → 创建草稿 → 发布"""
import logging
import os
from uuid import UUID
from typing import Any

logger = logging.getLogger(__name__)

# ── 环境变量配置 ──
WEIXIN_OA_APPID = os.getenv("WEIXIN_OA_APPID", "")
WEIXIN_OA_SECRET = os.getenv("WEIXIN_OA_SECRET", "")

# ── 微信 API 地址 ──
ACCESS_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
UPLOAD_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"
DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
PUBLISH_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/submit"


def dry_run(briefing: dict) -> str:
    """dry-run 模式：只生成 HTML，不调用任何微信 API

    使用 platforms/weixin.py 的 render_briefing_html（绿色 WeChat 品牌色系，
    带头条大图、标签、配图等丰富样式），替代 renderer.py 的简化版渲染。
    """
    from .weixin import render_briefing_html
    html = render_briefing_html(briefing)
    return html


async def get_access_token(appid: str = "", secret: str = "") -> str | None:
    """获取微信全局 access_token"""
    import httpx

    appid = appid or WEIXIN_OA_APPID
    secret = secret or WEIXIN_OA_SECRET

    if not appid or not secret:
        logger.warning("WEIXIN_OA_APPID or WEIXIN_OA_SECRET not configured")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(ACCESS_TOKEN_URL, params={
                "grant_type": "client_credential",
                "appid": appid,
                "secret": secret,
            })
            r.raise_for_status()
            data = r.json()
            if "access_token" in data:
                return data["access_token"]
            else:
                logger.error(f"微信 access_token 错误: {data}")
                return None
    except Exception as e:
        logger.error(f"获取 access_token 失败: {e}")
        return None


async def upload_image(token: str, file_path: str) -> str | None:
    """上传封面图到微信素材库（永久素材）"""
    import httpx

    if not token:
        return None

    try:
        url = f"{UPLOAD_URL}?access_token={token}&type=image"
        async with httpx.AsyncClient(timeout=30) as client:
            with open(file_path, "rb") as f:
                r = await client.post(url, files={"media": f})
            r.raise_for_status()
            data = r.json()
            if "media_id" in data:
                return data["media_id"]
            else:
                logger.error(f"上传图片失败: {data}")
                return None
    except FileNotFoundError:
        logger.error(f"图片文件不存在: {file_path}")
        return None
    except Exception as e:
        logger.error(f"上传图片异常: {e}")
        return None


async def create_draft(token: str, content: str, title: str = "AI 资讯简报",
                       thumb_media_id: str | None = None) -> str | None:
    """创建草稿，返回 media_id"""
    import httpx

    if not token:
        return None

    body = {
        "title": title,
        "content": content,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }
    if thumb_media_id:
        body["thumb_media_id"] = thumb_media_id

    # 微信草稿 body 需要包装在 articles 数组中
    payload = {"articles": [body]}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{DRAFT_URL}?access_token={token}",
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            if "media_id" in data:
                return data["media_id"]
            else:
                logger.error(f"创建草稿失败: {data}")
                return None
    except Exception as e:
        logger.error(f"创建草稿异常: {e}")
        return None


async def publish_draft(token: str, media_id: str) -> str | None:
    """发布草稿，返回 publish_id"""
    import httpx

    if not token or not media_id:
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{PUBLISH_URL}?access_token={token}",
                json={"media_id": media_id},
            )
            r.raise_for_status()
            data = r.json()
            if "publish_id" in data:
                return data["publish_id"]
            else:
                logger.error(f"发布草稿失败: {data}")
                return None
    except Exception as e:
        logger.error(f"发布草稿异常: {e}")
        return None


async def publish(pool, briefing_id: UUID, briefing: dict) -> dict:
    """主函数：dry_run → get_token → upload → draft → publish"""
    from datetime import datetime, timezone

    # Step 0: dry-run 生成 HTML
    html_content = dry_run(briefing)
    logger.info(f"[weixin_oa] dry_run HTML generated ({len(html_content)} chars)")

    title = f"AI 资讯{'早报' if briefing.get('type') == 'morning' else '晚报'} {briefing.get('date', '')}"

    # Step 1: 检查凭据
    if not WEIXIN_OA_APPID or not WEIXIN_OA_SECRET:
        logger.warning("[weixin_oa] 凭据未配置，跳过真发布")
        return {
            "platform": "weixin_oa",
            "status": "pending",
            "url": None,
            "error": "credentials not configured, dry_run HTML available",
        }

    # Step 2: 获取 token
    token = await get_access_token()
    if not token:
        return {
            "platform": "weixin_oa",
            "status": "failed",
            "url": None,
            "error": "failed to get access_token",
        }

    # Step 3: 创建草稿
    media_id = await create_draft(token, html_content, title)
    if not media_id:
        return {
            "platform": "weixin_oa",
            "status": "failed",
            "url": None,
            "error": "failed to create draft",
        }

    # Step 4: 发布
    publish_id = await publish_draft(token, media_id)
    if not publish_id:
        # 草稿创建成功但发布失败，仍可手动发布
        return {
            "platform": "weixin_oa",
            "status": "pending",
            "url": None,
            "error": "draft created but publish failed, publish manually from WeChat OA",
        }

    return {
        "platform": "weixin_oa",
        "status": "success",
        "url": f"https://mp.weixin.qq.com/s/{publish_id}",
        "error": None,
    }
