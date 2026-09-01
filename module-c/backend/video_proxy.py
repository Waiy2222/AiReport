"""Module-C → Module-F 视频服务代理

所有视频相关请求通过此模块代理到 Module-F (:8006)。
"""
import os
import httpx

VIDEO_SERVICE_URL = os.getenv("VIDEO_SERVICE_URL", "http://localhost:8006")


async def generate_video(keyword: str) -> dict:
    """触发视频生成，返回 {video_id, status, message}"""
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        r = await client.post(f"{VIDEO_SERVICE_URL}/generate", json={
            "keyword": keyword,
            "type": "ai_agent_weekly",
        })
        r.raise_for_status()
        return r.json()


async def get_video_status(video_id: str) -> dict:
    """查询视频生成状态"""
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        r = await client.get(f"{VIDEO_SERVICE_URL}/status/{video_id}")
        r.raise_for_status()
        return r.json()


async def list_videos(page: int = 1, size: int = 10) -> dict:
    """获取视频列表，返回分页格式 {items, total, page, size}"""
    offset = (page - 1) * size
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        r = await client.get(f"{VIDEO_SERVICE_URL}/videos", params={
            "limit": size, "offset": offset,
        })
        r.raise_for_status()
        data = r.json()
        # Module-F /videos 返回 list 或 {items, total}
        if isinstance(data, list):
            return {
                "items": data,
                "total": len(data),
                "page": page,
                "size": size,
            }
        return {
            "items": data.get("items", []),
            "total": data.get("total", len(data.get("items", []))),
            "page": page,
            "size": size,
        }


async def get_video_meta(video_id: str) -> dict:
    """获取视频元数据（含 output_path, cover_path），用于文件流式返回"""
    return await get_video_status(video_id)
