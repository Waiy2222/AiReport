"""Module E — 调度管理与 Dashboard (:8005)"""
import os
import json
import logging
from datetime import date
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db import get_pool, init_db, close_db
from pipeline import execute_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [E] %(message)s")
logger = logging.getLogger(__name__)

# ---------- 配置 ----------
SCHEDULE_ENABLED = os.getenv("SCHEDULE_ENABLED", "true").lower() == "true"
MORNING_TIME = os.getenv("MORNING_TIME", "08:00")  # 早报 8:00
EVENING_TIME = os.getenv("EVENING_TIME", "20:00")   # 晚报 20:00

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


# ---------- FastAPI ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except Exception:
        pass

    # 启动定时任务
    if SCHEDULE_ENABLED:
        morning_h, morning_m = map(int, MORNING_TIME.split(":"))
        evening_h, evening_m = map(int, EVENING_TIME.split(":"))

        scheduler.add_job(
            scheduled_trigger,
            CronTrigger(hour=morning_h, minute=morning_m, timezone="Asia/Shanghai"),
            args=["morning"],
            id="morning_schedule",
            replace_existing=True,
        )
        scheduler.add_job(
            scheduled_trigger,
            CronTrigger(hour=evening_h, minute=evening_m, timezone="Asia/Shanghai"),
            args=["evening"],
            id="evening_schedule",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(f"Scheduler started: morning={MORNING_TIME}, evening={EVENING_TIME}")

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
async def trigger(type: str = Query(..., description="morning or evening")):
    if type not in ("morning", "evening"):
        raise HTTPException(400, "type must be morning or evening")

    try:
        pool = get_pool()
        await pool.fetchval("SELECT 1")
    except RuntimeError:
        raise HTTPException(503, "database not initialized")
    except Exception:
        raise HTTPException(503, "database not available")

    try:
        result = await execute_pipeline(type)
        return result
    except Exception as e:
        raise HTTPException(500, f"pipeline failed: {e}")


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
    for m in ["A", "B", "C", "D", "E"]:
        row = await pool.fetchrow(
            "SELECT status FROM run_log WHERE module=$1 ORDER BY started_at DESC LIMIT 1", m
        )
        module_status[m] = row["status"] if row else "unknown"

    # 统计
    total_runs = await pool.fetchval("SELECT COUNT(*) FROM run_log")
    success_runs = await pool.fetchval("SELECT COUNT(*) FROM run_log WHERE status='success'")
    failed_runs = await pool.fetchval("SELECT COUNT(*) FROM run_log WHERE status='failed'")

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
        "morning_time": MORNING_TIME,
        "evening_time": EVENING_TIME,
        "timezone": "Asia/Shanghai",
        "jobs": jobs,
    }


# ---------- Dashboard Router ----------
from dashboard.backend.dashboard import router as dashboard_router
app.include_router(dashboard_router)

# ---------- Static file serving for dashboard frontend ----------
_frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "frontend", "src", "pages")
if os.path.isdir(_frontend_dir):
    app.mount("/dashboard", StaticFiles(directory=_frontend_dir, html=True), name="dashboard_static")
