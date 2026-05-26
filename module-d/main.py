"""Module D — 多平台发布 (:8004)"""
import asyncio
import os
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_pool, init_db, close_db
from platforms import zhihu, csdn, weixin

app = FastAPI(title="Module D - Multi-Platform Publisher")

PLATFORMS = ["zhihu", "csdn", "weixin_oa"]

_PLATFORM_MODULES = {
    "zhihu": zhihu,
    "csdn": csdn,
    "weixin_oa": weixin,
}

DRY_RUN_DIR = Path("dry-run-output")


@app.on_event("startup")
async def startup():
    try:
        await init_db()
    except Exception:
        pass


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
    briefing_id = uuid.UUID(req.briefing_id)

    for p in req.platforms:
        if p not in PLATFORMS:
            raise HTTPException(400, f"unsupported platform: {p}")

    pool = _get_pool_or_503()

    # Fetch full briefing record
    briefing = await pool.fetchrow(
        """SELECT id, type, date, tl_dr, sections, key_takeaways
           FROM briefings WHERE id = $1""",
        briefing_id,
    )
    if not briefing:
        raise HTTPException(404, "briefing not found")

    # Run all platforms concurrently — failures are independent
    results = await asyncio.gather(
        *[_publish_to(pool, briefing, p, dry_run=req.dry_run) for p in req.platforms],
        return_exceptions=True,
    )

    # Unwrap exceptions into error dicts
    final_results: list[dict] = []
    for platform, result in zip(req.platforms, results):
        if isinstance(result, Exception):
            final_results.append({
                "platform": platform,
                "status": "failed",
                "url": None,
                "error": str(result),
            })
        else:
            final_results.append(result)

    return {
        "briefing_id": str(briefing_id),
        "dry_run": req.dry_run,
        "results": final_results,
    }


async def _publish_to(pool, briefing, platform: str, dry_run: bool = False) -> dict:
    """Publish a briefing to a single platform.

    1. Check credentials; skip with "pending" if not configured.
    2. Convert briefing to the platform's content format.
    3. INSERT a pending log row into publish_log.
    4. Call the platform-specific publish function.
    5. UPDATE the log row on success or failure.

    When ``dry_run=True``, content is written to ``dry-run-output/`` as a file
    instead of calling live APIs.
    """
    # ── Dry-run path ──────────────────────────────────────────────
    if dry_run:
        return await _dry_run_publish(briefing, platform)

    # ── Credentials pre-check ─────────────────────────────────────
    if not _credentials_configured(platform):
        return {
            "platform": platform,
            "status": "pending",
            "url": None,
            "error": "API credentials not configured",
        }

    module = _PLATFORM_MODULES[platform]

    # ── Convert briefing to publishable content ────────────────────
    title = briefing_to_title(briefing)

    if platform == "weixin_oa":
        content = weixin.render_briefing_html(briefing)
        tags = None
    else:
        content = briefing_to_markdown(briefing)
        tags = extract_tags_from_briefing(briefing) if platform == "csdn" else None

    # ── Record pending attempt in publish_log ──────────────────────
    log_id = await pool.fetchval(
        """INSERT INTO publish_log (briefing_id, platform, status)
           VALUES ($1, $2, 'pending')
           RETURNING id""",
        briefing["id"],
        platform,
    )

    # ── Call the platform publish function ─────────────────────────
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if platform == "csdn":
                result = await module.publish(client, title, content, tags)
            else:
                result = await module.publish(client, title, content)

        if result.get("url"):
            await pool.execute(
                """UPDATE publish_log
                   SET status = 'success', platform_url = $1, published_at = now()
                   WHERE id = $2""",
                result["url"],
                log_id,
            )
            return {
                "platform": platform,
                "status": "success",
                "url": result["url"],
                "error": None,
            }
        else:
            error_msg = result.get("error", "Unknown error")
            await pool.execute(
                """UPDATE publish_log
                   SET status = 'failed', error_msg = $1
                   WHERE id = $2""",
                error_msg,
                log_id,
            )
            return {
                "platform": platform,
                "status": "failed",
                "url": None,
                "error": error_msg,
            }

    except Exception as exc:
        error_msg = str(exc)
        await pool.execute(
            """UPDATE publish_log
               SET status = 'failed', error_msg = $1
               WHERE id = $2""",
            error_msg,
            log_id,
        )
        return {
            "platform": platform,
            "status": "failed",
            "url": None,
            "error": error_msg,
        }


async def _dry_run_publish(briefing, platform: str) -> dict:
    """Generate publishable content and write it to a local file.

    Does NOT call any live API and does NOT touch publish_log.
    """
    DRY_RUN_DIR.mkdir(parents=True, exist_ok=True)

    title = briefing_to_title(briefing)
    briefing_id = str(briefing["id"])
    safe_date = str(briefing["date"]).replace(":", "-")

    if platform == "weixin_oa":
        content = weixin.render_briefing_html(briefing)
        ext = "html"
    else:
        content = briefing_to_markdown(briefing)
        ext = "md"

    filename = f"{platform}_{safe_date}_{briefing_id[:8]}.{ext}"
    filepath = DRY_RUN_DIR / filename
    filepath.write_text(content, encoding="utf-8")

    return {
        "platform": platform,
        "status": "dry_run",
        "url": str(filepath.resolve()),
        "error": None,
    }
