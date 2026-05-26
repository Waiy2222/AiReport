"""Module A — 资讯抓取 (:8001)"""
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_pool, init_db, close_db
from scrapers import SCRAPERS

logger = logging.getLogger(__name__)

app = FastAPI(title="Module A - News Fetcher")

SOURCES = ["github", "hackernews", "rss", "reddit"]


@app.on_event("startup")
async def startup():
    try:
        await init_db()
    except Exception:
        pass  # 允许无 DB 启动，/health 会报告状态


@app.on_event("shutdown")
async def shutdown():
    await close_db()


class FetchRequest(BaseModel):
    batch_id: str
    hours_back: int = 12


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


@app.post("/run")
async def run(req: FetchRequest):
    batch_id = uuid.UUID(req.batch_id)
    since = datetime.now(timezone.utc) - timedelta(hours=req.hours_back)

    pool = _get_pool_or_503()
    fetched = 0
    per_source = {}

    for source in SOURCES:
        count = await _fetch_source(pool, source, since, batch_id)
        per_source[source] = count
        fetched += count

    status = "ok" if all(v > 0 for v in per_source.values()) else "partial"

    return {
        "status": status,
        "fetched": fetched,
        "batch_id": str(batch_id),
        "per_source": per_source,
    }


async def _fetch_source(pool, source: str, since: datetime, batch_id: uuid.UUID) -> int:
    """Fetch items from the given source and insert into raw_items.

    Dispatches to the appropriate scraper module.  Each scraper handles its
    own errors — no exception is allowed to bubble up and crash the /run
    endpoint.
    """
    fetch_fn = SCRAPERS.get(source)
    if fetch_fn is None:
        logger.warning("Unknown source: %s", source)
        return 0

    try:
        count = await fetch_fn(pool, since, batch_id)
        logger.info("Source '%s': %d items inserted", source, count)
        return count
    except Exception:
        logger.exception("Source '%s' raised an unhandled exception", source)
        return 0
