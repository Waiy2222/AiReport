"""Module A — 资讯抓取 (:8001)"""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db import get_pool, init_db, close_db
from scrapers import SCRAPERS

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

app = FastAPI(title="Module A - News Fetcher")

SOURCES = ["github", "hackernews", "rss"]  # reddit/twitter 为可选 P1，按需添加


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
    batch_id: uuid.UUID = Field(..., description="批次唯一标识")
    hours_back: int = Field(default=12, ge=1, le=168, description="回溯小时数")


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
    since = datetime.now(timezone.utc) - timedelta(hours=req.hours_back)
    pool = get_pool()

    from orchestrator import run_all_scrapers, bulk_insert

    # 并发抓取
    items, per_source = await run_all_scrapers(since, req.batch_id, SOURCES)

    # 批量写入数据库
    inserted = await bulk_insert(pool, items)

    all_zero = all(v == 0 for v in per_source.values())
    status = "partial" if all_zero else "ok"

    return {
        "status": status,
        "fetched": inserted,
        "batch_id": str(req.batch_id),
        "per_source": per_source,
    }
