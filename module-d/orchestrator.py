"""多平台并发发布编排 — 并发执行 + 失败隔离 + publish_log 写入"""
import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID
from typing import Any

logger = logging.getLogger(__name__)

PLATFORM_TIMEOUT = 60  # 单平台发布超时秒数

# 平台模块映射
_PLATFORM_MODULES = {
    "weixin_oa": "platforms.weixin_oa",
    "zhihu": "platforms.zhihu",
    "csdn": "platforms.csdn",
}


async def write_log(
    pool,
    briefing_id: UUID,
    platform: str,
    status: str,
    platform_url: str | None = None,
    error: str | None = None,
) -> None:
    """写 publish_log 表"""
    published_at = datetime.now(timezone.utc) if status == "success" else None
    await pool.execute(
        """INSERT INTO publish_log (briefing_id, platform, status, platform_url, error_msg, published_at)
           VALUES ($1, $2, $3, $4, $5, $6)""",
        briefing_id,
        platform,
        status,
        platform_url,
        error,
        published_at,
    )


async def _publish_one(
    pool, briefing_id: UUID, briefing: dict, platform: str
) -> dict:
    """调用对应平台的 publish()，超时/异常保护"""
    module_path = _PLATFORM_MODULES.get(platform)
    if module_path is None:
        logger.warning(f"[orchestrator] Unknown platform: {platform}")
        return {
            "platform": platform,
            "status": "failed",
            "url": None,
            "error": f"unsupported platform: {platform}",
        }

    import importlib

    module = importlib.import_module(module_path)

    try:
        result = await asyncio.wait_for(
            module.publish(pool, briefing_id, briefing),
            timeout=PLATFORM_TIMEOUT,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning(f"[orchestrator] {platform} timed out after {PLATFORM_TIMEOUT}s")
        return {
            "platform": platform,
            "status": "failed",
            "url": None,
            "error": f"timeout after {PLATFORM_TIMEOUT}s",
        }
    except Exception as e:
        logger.warning(f"[orchestrator] {platform} failed: {e}")
        return {
            "platform": platform,
            "status": "failed",
            "url": None,
            "error": str(e),
        }


async def publish_all(
    pool, briefing_id: UUID, briefing: dict, platforms: list[str]
) -> list[dict]:
    """并发执行各平台发布，单平台失败不影响其他

    返回列表：各平台独立结果
    每条 result 自动写入 publish_log
    """
    if not platforms:
        return []

    # 并发执行
    tasks = [
        _publish_one(pool, briefing_id, briefing, p)
        for p in platforms
    ]
    results = await asyncio.gather(*tasks)

    # 写入 publish_log（无论成功失败）
    for result in results:
        try:
            await write_log(
                pool,
                briefing_id,
                result["platform"],
                result["status"],
                result.get("url"),
                result.get("error"),
            )
        except Exception as e:
            logger.error(f"[orchestrator] Failed to write publish_log for {result['platform']}: {e}")

    return results
