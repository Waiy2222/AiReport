"""CSDN 文章发布 — 生成 Markdown → 发布文章"""
import logging
import os
from uuid import UUID
from typing import Any

logger = logging.getLogger(__name__)

# ── 环境变量配置 ──
CSDN_ACCESS_TOKEN = os.getenv("CSDN_ACCESS_TOKEN", "")

# ── CSDN API 地址（待实测后确认） ──
ARTICLE_URL = "https://api.csdn.net/v2/articles"


def dry_run(briefing: dict) -> str:
    """dry-run 模式：只生成 Markdown，不调用 CSDN API"""
    from content import format_markdown
    md = format_markdown(briefing)
    return md


async def publish_article(token: str, title: str, content: str) -> str | None:
    """发布 CSDN 文章，返回 article_id"""
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
                    "type": "original",
                    "categories": ["人工智能", "AI", "开源"],
                    "tags": ["AI", "大模型", "Agent", "开源"],
                },
            )
            r.raise_for_status()
            data = r.json()
            if "id" in data:
                return str(data["id"])
            else:
                logger.error(f"CSDN 发布失败: {data}")
                return None
    except Exception as e:
        logger.error(f"CSDN 发布异常: {e}")
        return None


async def publish(pool, briefing_id: UUID, briefing: dict) -> dict:
    """主函数：dry_run → publish_article"""
    # Step 0: dry-run 生成 Markdown
    md_content = dry_run(briefing)
    logger.info(f"[csdn] dry_run Markdown generated ({len(md_content)} chars)")

    title = f"AI 资讯{'早报' if briefing.get('type') == 'morning' else '晚报'} {briefing.get('date', '')}"

    # Step 1: 检查凭据
    if not CSDN_ACCESS_TOKEN:
        logger.warning("[csdn] 凭据未配置，跳过真发布")
        return {
            "platform": "csdn",
            "status": "pending",
            "url": None,
            "error": "credentials not configured, dry_run Markdown available",
        }

    # Step 2: 发布
    article_id = await publish_article(CSDN_ACCESS_TOKEN, title, md_content)
    if not article_id:
        return {
            "platform": "csdn",
            "status": "failed",
            "url": None,
            "error": "failed to publish article",
        }

    return {
        "platform": "csdn",
        "status": "success",
        "url": f"https://blog.csdn.net/article/details/{article_id}",
        "error": None,
    }
