"""Pipeline execution functions — extracted for reuse by both main.py and dashboard.py."""
import uuid
import json
import asyncio
import logging
import os
from datetime import date

import httpx

from db import get_pool

logger = logging.getLogger(__name__)

A_URL = os.getenv("A_URL", "http://module-a:8001/run")
B_URL = os.getenv("B_URL", "http://module-b:8002/run-b")
C_URL = os.getenv("C_URL", "http://module-c:8003/push")
D_URL = os.getenv("D_URL", "http://module-d:8004/publish")
F_URL = os.getenv("F_URL", "http://module-f:8006/generate")


async def execute_pipeline(type_: str) -> dict:
    """Execute full pipeline A -> B -> C+D, write run_log entries."""
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

    # Step 1: A - fetch
    await log_step("A", "running")
    async with httpx.AsyncClient(timeout=180) as client:
        hours = 12
        try:
            r = await client.post(A_URL, json={"batch_id": batch_id, "hours_back": hours})
            r.raise_for_status()
            steps["fetch"] = r.json()
            await log_step("A", "success", steps["fetch"])
        except Exception as e:
            steps["fetch"] = {"status": "failed", "error": str(e)}
            await log_step("A", "failed", steps["fetch"])
            return {"status": "failed", "batch_id": batch_id, "type": type_, "steps": steps}

        # Step 2: B - AI process
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

        # Step 3: C + D in parallel
        if not briefing_id:
            return {"status": "failed", "batch_id": batch_id, "type": type_, "steps": steps,
                    "error": "no briefing_id from B"}

        await log_step("C", "running")
        await log_step("D", "running")

        c_result, d_result = await asyncio.gather(
            _do_push(client, briefing_id),
            _do_publish(client, briefing_id),
            return_exceptions=True,
        )

        for module, result in [("C", c_result), ("D", d_result)]:
            if isinstance(result, Exception):
                steps["push" if module == "C" else "publish"] = {
                    "status": "failed", "error": str(result)}
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


async def _do_push(client, briefing_id: str) -> dict:
    r = await client.post(C_URL, json={"briefing_id": briefing_id})
    r.raise_for_status()
    return r.json()


async def _do_publish(client, briefing_id: str) -> dict:
    r = await client.post(D_URL, json={"briefing_id": briefing_id})
    r.raise_for_status()
    return r.json()


async def execute_video_pipeline(type_: str = "ai_agent_weekly",
                                 gen_date: str | None = None) -> dict:
    """Execute video generation pipeline (independent, manual trigger only).

    Video generation is NOT chained to the doc pipeline — it's triggered
    manually via POST /admin/trigger-video.  Failure here does not affect
    document briefings.
    """
    video_id = str(uuid.uuid4())
    pool = get_pool()

    payload: dict = {"type": type_}
    if gen_date:
        payload["date"] = gen_date

    # Log start
    step_id = str(uuid.uuid4())
    await pool.execute(
        """INSERT INTO run_log (id, module, run_type, status, started_at, detail)
           VALUES ($1, 'F', $2, 'running', now(), $3::jsonb)""",
        uuid.UUID(step_id),
        type_,
        json.dumps({"video_id": video_id, "gen_date": gen_date}),
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(F_URL, json=payload)
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        logger.error(f"Video generation trigger failed: {e}")
        await pool.execute(
            """UPDATE run_log SET status='failed', finished_at=now(),
               detail=detail || $1::jsonb WHERE id=$2""",
            json.dumps({"error": str(e)}),
            uuid.UUID(step_id),
        )
        return {"status": "failed", "video_id": video_id, "error": str(e)}

    # Update log on success
    await pool.execute(
        """UPDATE run_log SET status='success', finished_at=now(),
           detail=detail || $1::jsonb WHERE id=$2""",
        json.dumps(result),
        uuid.UUID(step_id),
    )

    return {
        "status": "ok",
        "video_id": result.get("video_id", video_id),
        "module_f_response": result,
    }
