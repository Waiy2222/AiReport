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
            _do_push(client, type_),
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


async def _do_push(client, type_: str) -> dict:
    r = await client.post(C_URL, json={"type": type_})
    r.raise_for_status()
    return r.json()


async def _do_publish(client, briefing_id: str) -> dict:
    r = await client.post(D_URL, json={"briefing_id": briefing_id})
    r.raise_for_status()
    return r.json()
