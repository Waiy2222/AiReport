"""Module E — 调度管理与 Dashboard (:8005)"""
import os
import uuid
import asyncio
from datetime import datetime, date, timezone

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from db import get_pool, init_db, close_db

app = FastAPI(title="Module E - Scheduler & Dashboard")

# 模块内部 URL（Docker 网络内）
A_URL = os.getenv("A_URL", "http://module-a:8001/run")
B_URL = os.getenv("B_URL", "http://module-b:8002/run-b")
C_URL = os.getenv("C_URL", "http://module-c:8003/push")
D_URL = os.getenv("D_URL", "http://module-d:8004/publish")


@app.on_event("startup")
async def startup():
    try:
        await init_db()
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown():
    await close_db()


@app.get("/health")
async def health():
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception:
        return {"status": "ok", "db": "disconnected"}


@app.post("/admin/trigger")
async def trigger(type: str = Query(..., description="morning or evening")):
    if type not in ("morning", "evening"):
        raise HTTPException(400, "type must be morning or evening")

    batch_id = str(uuid.uuid4())
    today = date.today().isoformat()
    run_id = str(uuid.uuid4())

    pool = get_pool()

    # 记录运行开始
    await pool.execute(
        "INSERT INTO run_log (id, module, run_type, status, started_at) VALUES ($1, 'E', $2, 'running', now())",
        uuid.UUID(run_id), type,
    )

    import httpx

    result = {
        "run_id": run_id,
        "type": type,
        "batch_id": batch_id,
        "steps": {},
    }

    async with httpx.AsyncClient(timeout=120) as client:
        # Step 1: A — 抓取资讯
        hours = 12 if type == "morning" else 12
        try:
            r = await client.post(A_URL, json={"batch_id": batch_id, "hours_back": hours})
            result["steps"]["fetch"] = r.json()
        except Exception as e:
            result["steps"]["fetch"] = {"status": "failed", "error": str(e)}

        # Step 2: B — AI 加工
        briefing_id = None
        try:
            r = await client.post(B_URL, json={"type": type, "date": today, "batch_id": batch_id})
            briefing_data = r.json()
            result["steps"]["process"] = briefing_data
            briefing_id = briefing_data.get("briefing_id")
        except Exception as e:
            result["steps"]["process"] = {"status": "failed", "error": str(e)}

        # Step 3: C + D 并行
        if briefing_id:
            c_task = _call_push(client, type)
            d_task = _call_publish(client, briefing_id)
            c_result, d_result = await asyncio.gather(c_task, d_task, return_exceptions=True)
            result["steps"]["push"] = c_result if not isinstance(c_result, Exception) else {"status": "failed", "error": str(c_result)}
            result["steps"]["publish"] = d_result if not isinstance(d_result, Exception) else {"status": "failed", "error": str(d_result)}

    await pool.execute(
        "UPDATE run_log SET status='success', finished_at=now(), detail=$1 WHERE id=$2",
        result, uuid.UUID(run_id),
    )

    return result


async def _call_push(client, type_: str) -> dict:
    r = await client.post(C_URL, json={"type": type_})
    return r.json()


async def _call_publish(client, briefing_id: str) -> dict:
    r = await client.post(D_URL, json={"briefing_id": briefing_id})
    return r.json()


@app.get("/admin/overview")
async def overview():
    pool = get_pool()
    today = date.today()

    # 今日简报状态
    am = await pool.fetchrow(
        "SELECT id, generated_at FROM briefings WHERE type='morning' AND date=$1", today
    )
    pm = await pool.fetchrow(
        "SELECT id, generated_at FROM briefings WHERE type='evening' AND date=$1", today
    )

    # 各模块最近运行记录
    recent = await pool.fetch(
        "SELECT module, run_type, status, started_at, finished_at, detail "
        "FROM run_log ORDER BY started_at DESC LIMIT 20"
    )

    return {
        "date": today.isoformat(),
        "morning": {
            "status": "done" if am else "pending",
            "briefing_id": str(am["id"]) if am else None,
            "generated_at": am["generated_at"].isoformat() if am else None,
        },
        "evening": {
            "status": "done" if pm else "pending",
            "briefing_id": str(pm["id"]) if pm else None,
            "generated_at": pm["generated_at"].isoformat() if pm else None,
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
