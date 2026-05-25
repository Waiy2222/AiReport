"""Module E — 调度管理与 Dashboard (:8005)"""
import os
import uuid
import json
import asyncio
import logging
from datetime import datetime, date, time, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db import get_pool, init_db, close_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [E] %(message)s")
logger = logging.getLogger(__name__)

# ---------- 配置 ----------
A_URL = os.getenv("A_URL", "http://module-a:8001/run")
B_URL = os.getenv("B_URL", "http://module-b:8002/run-b")
C_URL = os.getenv("C_URL", "http://module-c:8003/push")
D_URL = os.getenv("D_URL", "http://module-d:8004/publish")

SCHEDULE_ENABLED = os.getenv("SCHEDULE_ENABLED", "true").lower() == "true"
MORNING_TIME = os.getenv("MORNING_TIME", "08:00")  # 早报 8:00
EVENING_TIME = os.getenv("EVENING_TIME", "20:00")   # 晚报 20:00

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


# ---------- 调度任务 ----------
async def scheduled_trigger(type_: str):
    """定时任务入口：被 APScheduler 调用"""
    logger.info(f"Scheduled trigger: {type_}")
    try:
        result = await _execute_pipeline(type_)
        logger.info(f"Scheduled {type_} done: {json.dumps(result, default=str)[:200]}")
    except Exception as e:
        logger.error(f"Scheduled {type_} failed: {e}")


async def _execute_pipeline(type_: str) -> dict:
    """执行完整流水线 A → B → C+D，写 run_log"""
    import httpx

    batch_id = str(uuid.uuid4())
    today = date.today().isoformat()
    pool = get_pool()

    steps = {}

    async def log_step(module: str, status: str, detail: dict | None = None):
        step_id = str(uuid.uuid4())
        await pool.execute(
            """INSERT INTO run_log (id, module, run_type, status, started_at, finished_at, detail)
               VALUES ($1, $2, $3, $4, now(),
                       CASE WHEN $4 != 'running' THEN now() ELSE NULL END,
                       COALESCE($5::jsonb, '{}'))""",
            uuid.UUID(step_id), module, type_, status,
            json.dumps(detail) if detail else None,
        )
        return step_id

    # Step 1: A — 资讯抓取
    await log_step("A", "running")
    async with httpx.AsyncClient(timeout=180) as client:
        hours = 12  # morning 和 evening 都往前抓12小时
        try:
            r = await client.post(A_URL, json={"batch_id": batch_id, "hours_back": hours})
            r.raise_for_status()
            steps["fetch"] = r.json()
            await log_step("A", "success", steps["fetch"])
        except Exception as e:
            steps["fetch"] = {"status": "failed", "error": str(e)}
            await log_step("A", "failed", steps["fetch"])
            return {"status": "failed", "batch_id": batch_id, "type": type_, "steps": steps}

        # Step 2: B — AI 内容加工
        await log_step("B", "running")
        briefing_id = None
        try:
            r = await client.post(B_URL, json={"type": type_, "date": today, "batch_id": batch_id})
            r.raise_for_status()
            steps["process"] = r.json()
            briefing_id = steps["process"].get("briefing_id")
            await log_step("B", "success", steps["process"])
        except Exception as e:
            steps["process"] = {"status": "failed", "error": str(e)}
            await log_step("B", "failed", steps["process"])
            return {"status": "failed", "batch_id": batch_id, "type": type_, "steps": steps}

        # Step 3: C + D 并行
        if not briefing_id:
            return {"status": "failed", "batch_id": batch_id, "type": type_, "steps": steps, "error": "no briefing_id from B"}

        await log_step("C", "running")
        await log_step("D", "running")

        c_result, d_result = await asyncio.gather(
            _do_push(client, type_),
            _do_publish(client, briefing_id),
            return_exceptions=True,
        )

        for module, result in [("C", c_result), ("D", d_result)]:
            if isinstance(result, Exception):
                steps["push" if module == "C" else "publish"] = {"status": "failed", "error": str(result)}
                await log_step(module, "failed", {"error": str(result)})
            else:
                steps["push" if module == "C" else "publish"] = result
                await log_step(module, "success", result)

    return {
        "status": "ok",
        "batch_id": batch_id,
        "type": type_,
        "briefing_id": briefing_id,
        "steps": steps,
    }


async def _do_push(client, type_: str) -> dict:
    r = await client.post(C_URL, json={"type": type_})
    r.raise_for_status()
    return r.json()


async def _do_publish(client, briefing_id: str) -> dict:
    r = await client.post(D_URL, json={"briefing_id": briefing_id})
    r.raise_for_status()
    return r.json()


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
        result = await _execute_pipeline(type)
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
