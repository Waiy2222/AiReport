"""Module E — 调度管理与 Dashboard (:8005)"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

import json
import logging
from datetime import date, datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from db import get_pool, init_db, close_db
from pipeline import execute_pipeline, execute_video_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [E] %(message)s")
logger = logging.getLogger(__name__)

# ---------- 配置 ----------
SCHEDULE_ENABLED = os.getenv("SCHEDULE_ENABLED", "true").lower() == "true"

# 多时段调度：逗号分隔的时间列表，如 "06:00,08:00,10:00,12:00"
# 兼容旧变量 MORNING_TIME / EVENING_TIME（单时段）
def _parse_times(env_key: str, fallback: str) -> list[str]:
    raw = os.getenv(env_key, "")
    if not raw:
        # 兼容旧变量: MORNING_TIME / EVENING_TIME
        old_key = env_key.replace("_TIMES", "_TIME")
        raw = os.getenv(old_key, fallback)
    return [t.strip() for t in raw.split(",") if t.strip()]

MORNING_TIMES = _parse_times("MORNING_TIMES", "08:00")
EVENING_TIMES = _parse_times("EVENING_TIMES", "20:00")

# 间隔调度（分钟）：如果设置了这个，用 IntervalTrigger 替代 CronTrigger
# 例如 SCHEDULE_INTERVAL_MINUTES=120 表示每2小时跑一次
_SCHEDULE_INTERVAL_STR = os.getenv("SCHEDULE_INTERVAL_MINUTES", "")
SCHEDULE_INTERVAL_MINUTES = int(_SCHEDULE_INTERVAL_STR) if _SCHEDULE_INTERVAL_STR else None

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


# ---------- 调度任务 ----------
async def scheduled_trigger(type_: str):
    """定时任务入口：被 APScheduler 调用"""
    logger.info(f"Scheduled trigger: {type_}")
    try:
        result = await execute_pipeline(type_)
        logger.info(f"Scheduled {type_} done: {json.dumps(result, default=str)[:200]}")
    except Exception as e:
        logger.error(f"Scheduled {type_} failed: {e}")


async def scheduled_interval_trigger():
    """间隔模式：每 N 分钟自动触发一次，根据当前时间决定是早报还是晚报"""
    now = datetime.now()
    # 14:00 前算早报时段，之后算晚报时段
    type_ = "morning" if now.hour < 14 else "evening"
    await scheduled_trigger(type_)


# ---------- FastAPI ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except Exception:
        pass

    # 启动定时任务
    if SCHEDULE_ENABLED:
        if SCHEDULE_INTERVAL_MINUTES:
            # 间隔模式：每 N 分钟自动跑一次
            scheduler.add_job(
                scheduled_interval_trigger,
                IntervalTrigger(minutes=SCHEDULE_INTERVAL_MINUTES, timezone="Asia/Shanghai"),
                id="interval_schedule",
                replace_existing=True,
            )
            scheduler.start()
            logger.info(f"Scheduler started: interval mode, every {SCHEDULE_INTERVAL_MINUTES} min")
        else:
            # 多时段 Cron 模式
            for i, t in enumerate(MORNING_TIMES):
                h, m = t.split(":")
                scheduler.add_job(
                    scheduled_trigger,
                    CronTrigger(hour=int(h), minute=int(m), timezone="Asia/Shanghai"),
                    args=["morning"],
                    id=f"morning_schedule_{i}",
                    replace_existing=True,
                )
            for i, t in enumerate(EVENING_TIMES):
                h, m = t.split(":")
                scheduler.add_job(
                    scheduled_trigger,
                    CronTrigger(hour=int(h), minute=int(m), timezone="Asia/Shanghai"),
                    args=["evening"],
                    id=f"evening_schedule_{i}",
                    replace_existing=True,
                )
            scheduler.start()
            logger.info(f"Scheduler started: morning={MORNING_TIMES}, evening={EVENING_TIMES}")

    yield

    if SCHEDULE_ENABLED and scheduler.running:
        scheduler.shutdown(wait=False)
    await close_db()


app = FastAPI(title="Module E - Scheduler & Dashboard", lifespan=lifespan)

# ---------- CORS (allow dashboard from any origin) ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 健康检查 ----------
@app.get("/health")
async def health():
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok",
        "db": "connected" if db_ok else "disconnected",
        "scheduler": scheduler.running if SCHEDULE_ENABLED else False,
    }


# ---------- 手动触发全链路 ----------
@app.post("/admin/trigger")
async def trigger(type: str = Query(..., description="morning or evening"),
                  tags: str = Query("", description="逗号分隔标签，如 LLM,Agent"),
                  gen_date: str = Query(None, description="指定日期 YYYY-MM-DD，默认今天")):
    if type not in ("morning", "evening"):
        raise HTTPException(400, "type must be morning or evening")

    filter_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    try:
        pool = get_pool()
        await pool.fetchval("SELECT 1")
    except RuntimeError:
        raise HTTPException(503, "database not initialized")
    except Exception:
        raise HTTPException(503, "database not available")

    try:
        result = await execute_pipeline(type, filter_tags=filter_tags, gen_date=gen_date)
        return result
    except Exception as e:
        raise HTTPException(500, f"pipeline failed: {e}")


# ---------- 手动触发视频生成 ----------
@app.post("/admin/trigger-video")
async def trigger_video(
    type: str = Query("ai_agent_weekly", description="video type"),
    gen_date: str = Query(None, description="date in YYYY-MM-DD format"),
):
    """Manually trigger Module F video generation (independent of doc pipeline)."""
    try:
        pool = get_pool()
        await pool.fetchval("SELECT 1")
    except RuntimeError:
        raise HTTPException(503, "database not initialized")
    except Exception:
        raise HTTPException(503, "database not available")

    try:
        result = await execute_video_pipeline(type, gen_date)
        return result
    except Exception as e:
        raise HTTPException(500, f"video pipeline failed: {e}")


# ---------- 运行总览 ----------
@app.get("/admin/overview")
async def overview():
    try:
        pool = get_pool()
    except RuntimeError:
        raise HTTPException(503, "database not initialized")

    today = date.today()

    # 今日简报
    am = await pool.fetchrow(
        "SELECT id, type, generated_at, raw_stats FROM briefings WHERE type='morning' AND date=$1", today
    )
    pm = await pool.fetchrow(
        "SELECT id, type, generated_at, raw_stats FROM briefings WHERE type='evening' AND date=$1", today
    )

    # 最近 20 条运行记录
    recent = await pool.fetch(
        """SELECT module, run_type, status, started_at, finished_at, detail
           FROM run_log ORDER BY started_at DESC LIMIT 20"""
    )

    # 各模块最新状态
    module_status = {}
    for m in ["A", "B", "C", "D", "E", "F"]:
        row = await pool.fetchrow(
            "SELECT status FROM run_log WHERE module=$1 ORDER BY started_at DESC LIMIT 1", m
        )
        module_status[m] = row["status"] if row else "unknown"

    # 统计
    total_runs = await pool.fetchval("SELECT COUNT(*) FROM run_log")
    success_runs = await pool.fetchval("SELECT COUNT(*) FROM run_log WHERE status='success'")
    failed_runs = await pool.fetchval("SELECT COUNT(*) FROM run_log WHERE status='failed'")

    # 视频统计
    video_total = await pool.fetchval("SELECT COUNT(*) FROM videos")
    video_done = await pool.fetchval("SELECT COUNT(*) FROM videos WHERE status='done'")
    video_recent = await pool.fetch(
        """SELECT id, title, status, duration_seconds, created_at
           FROM videos ORDER BY created_at DESC LIMIT 5"""
    )

    return {
        "date": today.isoformat(),
        "morning": {
            "status": "done" if am else "pending",
            "briefing_id": str(am["id"]) if am else None,
            "generated_at": am["generated_at"].isoformat() if am else None,
            "raw_stats": am["raw_stats"] if am else None,
        },
        "evening": {
            "status": "done" if pm else "pending",
            "briefing_id": str(pm["id"]) if pm else None,
            "generated_at": pm["generated_at"].isoformat() if pm else None,
            "raw_stats": pm["raw_stats"] if pm else None,
        },
        "modules": module_status,
        "stats": {
            "total_runs": total_runs,
            "success": success_runs,
            "failed": failed_runs,
        },
        "recent_runs": [
            {
                "module": r["module"],
                "run_type": r["run_type"],
                "status": r["status"],
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
            }
            for r in recent
        ],
        "videos": {
            "total": video_total,
            "done": video_done,
            "recent": [
                {
                    "id": str(v["id"]),
                    "title": v["title"],
                    "status": v["status"],
                    "duration_seconds": v["duration_seconds"],
                    "created_at": v["created_at"].isoformat() if v["created_at"] else None,
                }
                for v in video_recent
            ],
        },
    }


# ---------- 调度状态 ----------
@app.get("/admin/schedule")
async def schedule_status():
    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
    return {
        "scheduler_running": scheduler.running,
        "enabled": SCHEDULE_ENABLED,
        "morning_times": MORNING_TIMES,
        "evening_times": EVENING_TIMES,
        "interval_minutes": SCHEDULE_INTERVAL_MINUTES,
        "timezone": "Asia/Shanghai",
        "jobs": jobs,
    }


# ---------- Proxy to module-c (source health / recommendations) ----------
C_URL = os.getenv("C_URL", "http://module-c:8003")


async def _proxy_get(url: str, params: dict | None = None, timeout: int = 30) -> httpx.Response:
    """Helper: GET proxy with configurable timeout."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r


async def _proxy_get_raw(url: str, timeout: int = 30) -> httpx.Response:
    """Helper: GET proxy that returns raw response (for binary/non-JSON content)."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
        if r.status_code >= 400:
            raise HTTPException(r.status_code, "upstream error")
        return r


@app.get("/api/sources/health")
async def proxy_sources_health():
    """Forward source health requests to module-c."""
    r = await _proxy_get(f"{C_URL}/api/sources/health")
    return r.json()


@app.get("/api/sources/recommendations")
async def proxy_sources_recommendations(
    status: str = Query("pending", description="pending | approved | rejected"),
):
    """Forward source recommendations requests to module-c."""
    r = await _proxy_get(f"{C_URL}/api/sources/recommendations", params={"status": status})
    return r.json()


@app.post("/api/sources/approve")
async def proxy_sources_approve(
    source_id: str = Query(..., description="推荐信源 ID"),
):
    """Forward source approval requests to module-c."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{C_URL}/api/sources/approve",
            params={"source_id": source_id},
        )
        if r.status_code >= 400:
            raise HTTPException(r.status_code, r.text)
        return r.json()


# ---------- Dashboard Router ----------
from dashboard.backend.dashboard import router as dashboard_router
app.include_router(dashboard_router)


# ---------- Proxy to module-b (preview / longimage) ----------
def _derive_base_url(url: str) -> str:
    """Extract scheme+host from a full endpoint URL (e.g. 'http://x:8002/run-b' → 'http://x:8002')."""
    from urllib.parse import urlparse, urlunparse
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, "", "", "", ""))


B_PROXY_URL = _derive_base_url(os.getenv("B_URL", "http://module-b:8002/run-b"))


@app.get("/preview/{briefing_id}")
async def proxy_preview(briefing_id: str):
    """Forward preview requests to module-b so browser only needs port 8005."""
    r = await _proxy_get_raw(f"{B_PROXY_URL}/preview/{briefing_id}")
    return Response(content=r.text, media_type="text/html")


@app.get("/longimage/{briefing_id}")
async def proxy_longimage(briefing_id: str):
    """Forward longimage requests to module-b."""
    r = await _proxy_get_raw(f"{B_PROXY_URL}/longimage/{briefing_id}", timeout=60)
    return Response(content=r.content, media_type=r.headers.get("content-type", "image/png"))


F_PROXY_URL = _derive_base_url(os.getenv("F_URL", "http://module-f:8006/generate"))


@app.get("/cover/{video_id}")
async def proxy_cover(video_id: str):
    """Forward cover image requests to module-f."""
    r = await _proxy_get_raw(f"{F_PROXY_URL}/cover/{video_id}")
    return Response(content=r.content, media_type=r.headers.get("content-type", "image/jpeg"))

# ---------- Static file serving for dashboard frontend ----------
_frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "frontend", "src", "pages")
if os.path.isdir(_frontend_dir):
    app.mount("/dashboard", StaticFiles(directory=_frontend_dir, html=True), name="dashboard_static")
