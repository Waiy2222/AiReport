"""Module D — 多平台发布 + 长图生成 (:8004)"""
import json
import logging
import os
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from db import get_pool, init_db, close_db
from platforms import zhihu, csdn, weixin

app = FastAPI(title="Module D - Multi-Platform Publisher + Long Image")

PLATFORMS = ["zhihu", "csdn", "weixin_oa"]

# asyncpg 将 JSONB 列返回为 Python 字符串，需手动解析
_JSONB_FIELDS = {"tl_dr", "sections", "key_takeaways", "raw_stats"}

# Phase 2: 长图输出目录
OUTPUT_DIR = Path(__file__).parent / "output"


def _parse_briefing(row) -> dict:
    """将 asyncpg Record 转为 dict，并解析 JSONB 字符串字段"""
    briefing = dict(row)
    for field in _JSONB_FIELDS:
        val = briefing.get(field)
        if isinstance(val, str):
            try:
                briefing[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass  # 保持原值
    return briefing


@app.on_event("startup")
async def startup():
    try:
        await init_db()
    except Exception:
        pass
    # Phase 2: 确保 longimage 输出目录存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("shutdown")
async def shutdown():
    await close_db()


class PublishRequest(BaseModel):
    briefing_id: str
    platforms: list[str] = ["zhihu", "csdn", "weixin_oa"]
    dry_run: bool = False


@app.get("/health")
async def health():
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception:
        return {"status": "ok", "db": "disconnected"}


def _get_pool_or_503():
    try:
        return get_pool()
    except RuntimeError:
        raise HTTPException(503, "database not initialized")


# ── Markdown conversion ─────────────────────────────────────────────────────

def briefing_to_title(briefing) -> str:
    """Generate a publish-ready title from a briefing record."""
    type_label = "AI资讯早报" if briefing["type"] == "morning" else "AI资讯晚报"
    date_str = str(briefing["date"])
    return f"{type_label} | {date_str}"


def briefing_to_markdown(briefing) -> str:
    """Convert a briefing record (JSONB fields) into well-formatted Markdown.

    briefing is an asyncpg Record with fields: type, date, tl_dr, sections,
    key_takeaways.
    """
    type_label = "早报" if briefing["type"] == "morning" else "晚报"
    date_str = str(briefing["date"])

    lines: list[str] = []
    lines.append(f"# AI资讯{type_label} | {date_str}")
    lines.append("")

    # ── TL;DR  ────────────────────────────────────────────────────
    tl_dr = briefing["tl_dr"]
    if tl_dr:
        lines.append("## 今日要闻")
        lines.append("")
        for item in tl_dr:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Sections ──────────────────────────────────────────────────
    sections = briefing["sections"] or []
    for section in sections:
        section_title = section.get("title", "未分类")
        lines.append(f"## {section_title}")
        lines.append("")

        for item in section.get("items", []):
            item_title = item.get("title", "")
            summary = item.get("summary", "")
            score = item.get("score", 0)
            source = item.get("source", "")
            url = item.get("url", "")

            lines.append(f"### {item_title}")
            lines.append("")
            if summary:
                lines.append(summary)
                lines.append("")

            # Meta line
            meta_parts = []
            if source:
                meta_parts.append(f"来源：{source}")
            if score:
                meta_parts.append(f"评分：{score}")
            if url:
                meta_parts.append(f"[阅读原文]({url})")
            if meta_parts:
                lines.append("> " + " | ".join(meta_parts))
            lines.append("")

        lines.append("---")
        lines.append("")

    # ── Key Takeaways ─────────────────────────────────────────────
    takeaways = briefing["key_takeaways"] or []
    if takeaways:
        lines.append("## 核心要点")
        lines.append("")
        for i, point in enumerate(takeaways, 1):
            lines.append(f"{i}. {point}")
        lines.append("")

    return "\n".join(lines)


def extract_tags_from_briefing(briefing) -> list[str]:
    """Extract unique tags from all items across all sections."""
    tags: set[str] = set()
    sections = briefing["sections"] or []
    for section in sections:
        for item in section.get("items", []):
            for tag in item.get("tags", []):
                tags.add(tag)
    return sorted(tags)


# ── Publishing orchestration ────────────────────────────────────────────────

_CREDENTIAL_ENV_VARS = {
    "zhihu": ["ZHIHU_CLIENT_ID", "ZHIHU_CLIENT_SECRET"],
    "csdn": ["CSDN_USERNAME", "CSDN_PASSWORD"],
    "weixin_oa": ["WEIXIN_OA_APPID", "WEIXIN_OA_SECRET"],
}


def _credentials_configured(platform: str) -> bool:
    """Check whether the required env vars for a platform are set."""
    for var in _CREDENTIAL_ENV_VARS.get(platform, []):
        if not os.getenv(var, "").strip():
            return False
    return True


@app.post("/publish")
async def publish(req: PublishRequest):
    try:
        briefing_id = uuid.UUID(req.briefing_id)
    except ValueError:
        raise HTTPException(400, f"invalid briefing_id format: {req.briefing_id}")

    for p in req.platforms:
        if p not in PLATFORMS:
            raise HTTPException(400, f"unsupported platform: {p}")

    pool = _get_pool_or_503()

    # 读取完整简报数据（JSONB 字段需解析）
    row = await pool.fetchrow(
        "SELECT * FROM briefings WHERE id=$1", briefing_id
    )
    if not row:
        raise HTTPException(404, "briefing not found")
    briefing = _parse_briefing(row)

    # Phase 2: 长图生成（dry_run + 真实发布都生成）
    longimage_path = None
    try:
        from long_image import generate_long_image
        output_name = f"longimage_{str(briefing_id)[:8]}.png"
        output_path = str(OUTPUT_DIR / output_name)
        longimage_path = await generate_long_image(briefing, output_path)
    except Exception as e:
        logger.warning(f"Long image generation failed (non-blocking): {e}")

    # 通过 orchestrator 并发发布（仅非 dry_run 时）
    if req.dry_run:
        results = [
            {"platform": p, "status": "dry_run", "url": None, "error": None}
            for p in req.platforms
        ]
    else:
        from orchestrator import publish_all
        results = await publish_all(pool, briefing_id, briefing, req.platforms)

    response = {
        "briefing_id": str(briefing_id),
        "dry_run": req.dry_run,
        "results": results,
    }
    if longimage_path:
        response["longimage"] = longimage_path
    return response
