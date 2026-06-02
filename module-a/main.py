"""Module A — 资讯抓取 + LLM 智能筛选 (:8001)"""
import os, sys
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db import get_pool, init_db, close_db
from scrapers import SCRAPERS, _insert_items

logger = logging.getLogger(__name__)
app = FastAPI(title="Module A - News Fetcher")

SOURCES = ["github", "hackernews", "rss"]


@app.on_event("startup")
async def startup():
    try:
        await init_db()
    except Exception:
        pass


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
    """获取数据库连接池，未初始化则抛 503"""
    try:
        return get_pool()
    except RuntimeError:
        raise HTTPException(503, "database not initialized")


async def _fetch_source(pool, source: str, since: datetime, batch_id: uuid.UUID) -> int:
    """调度单个 scraper 并返回抓取条目数（DB 写入由 orchestrator.run_pipeline 统一处理）。

    注意：此函数仅用于集成测试验证 scraper 调度逻辑。
    生产流程走 orchestrator.run_pipeline → run_all_scrapers → bulk_insert。
    """
    scraper = SCRAPERS.get(source)
    if scraper is None:
        logger.warning(f"Unknown scraper: {source}")
        return 0
    try:
        items = await scraper(pool, since, batch_id)
        return len(items)
    except Exception as e:
        logger.warning(f"Scraper [{source}] failed: {e}")
        return 0


@app.post("/run")
async def run(req: FetchRequest):
    pool = _get_pool_or_503()
    since = datetime.now(timezone.utc) - timedelta(hours=req.hours_back)

    from orchestrator import run_pipeline

    result = await run_pipeline(pool, since, req.batch_id, SOURCES)

    all_zero = all(v == 0 for v in result["per_source"].values())
    status = "partial" if all_zero else "ok"

    return {
        "status": status,
        "fetched": result["fetched"],
        "llm_filtered": result["llm_filtered"],
        "batch_id": str(req.batch_id),
        "per_source": result["per_source"],
    }
