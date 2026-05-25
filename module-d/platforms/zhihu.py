"""知乎专栏发布 — 生成 Markdown → 发布文章"""
import logging
import os
from uuid import UUID
from typing import Any

logger = logging.getLogger(__name__)

# ── 环境变量配置 ──
ZHIHU_CLIENT_ID = os.getenv("ZHIHU_CLIENT_ID", "")
ZHIHU_CLIENT_SECRET = os.getenv("ZHIHU_CLIENT_SECRET", "")

# ── 知乎 API 地址（待实测后确认） ──
TOKEN_URL = "https://api.zhihu.com/oauth/token"
ARTICLE_URL = "https://api.zhihu.com/v2/articles"


def dry_run(briefing: dict) -> str:
    """dry-run 模式：只生成 Markdown，不调用知乎 API"""
    from content import format_markdown
    md = format_markdown(briefing)
    return md


async def get_token(client_id: str = "", secret: str = "") -> str | None:
    """获取知乎 access_token"""
    import httpx

    client_id = client_id or ZHIHU_CLIENT_ID
    secret = secret or ZHIHU_CLIENT_SECRET

    if not client_id or not secret:
        logger.warning("ZHIHU_CLIENT_ID or ZHIHU_CLIENT_SECRET not configured")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(TOKEN_URL, data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": secret,
            })
            r.raise_for_status()
            data = r.json()
            if "access_token" in data:
                return data["access_token"]
            else:
                logger.error(f"知乎 token 错误: {data}")
                return None
    except Exception as e:
        logger.error(f"获取知乎 token 失败: {e}")
        return None


async def publish_article(token: str, title: str, content: str) -> str | None:
    """发布知乎文章，返回 article_id"""
    import httpx

    if not token:
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                ARTICLE_URL,
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "title": title,
                    "content": content,
                    "topics": ["人工智能", "开源", "AI"],
                },
            )
            r.raise_for_status()
            data = r.json()
            if "id" in data:
                return str(data["id"])
            else:
                logger.error(f"知乎发布失败: {data}")
                return None
    except Exception as e:
        logger.error(f"知乎发布异常: {e}")
        return None


async def publish(pool, briefing_id: UUID, briefing: dict) -> dict:
    """主函数：dry_run → get_token → publish_article"""
    # Step 0: dry-run 生成 Markdown
    md_content = dry_run(briefing)
    logger.info(f"[zhihu] dry_run Markdown generated ({len(md_content)} chars)")

    title = f"AI 资讯{'早报' if briefing.get('type') == 'morning' else '晚报'} {briefing.get('date', '')}"

    # Step 1: 检查凭据
    if not ZHIHU_CLIENT_ID or not ZHIHU_CLIENT_SECRET:
        logger.warning("[zhihu] 凭据未配置，跳过真发布")
        return {
            "platform": "zhihu",
            "status": "pending",
            "url": None,
            "error": "credentials not configured, dry_run Markdown available",
        }

    # Step 2: 获取 token
    token = await get_token()
    if not token:
        return {
            "platform": "zhihu",
            "status": "failed",
            "url": None,
            "error": "failed to get access_token",
        }

    # Step 3: 发布
    article_id = await publish_article(token, title, md_content)
    if not article_id:
        return {
            "platform": "zhihu",
            "status": "failed",
            "url": None,
            "error": "failed to publish article",
        }

    return {
        "platform": "zhihu",
        "status": "success",
        "url": f"https://zhuanlan.zhihu.com/p/{article_id}",
        "error": None,
    }
