"""Pipeline execution functions — extracted for reuse by both main.py and dashboard.py."""
import uuid
import json
import asyncio
import logging
import os
import time
from datetime import date, datetime, timezone

import httpx

from db import get_pool

logger = logging.getLogger(__name__)

A_URL = os.getenv("A_URL", "http://module-a:8001/run")
B_URL = os.getenv("B_URL", "http://module-b:8002/run-b")
C_URL = os.getenv("C_URL", "http://module-c:8003/push")
D_URL = os.getenv("D_URL", "http://module-d:8004/publish")
F_URL = os.getenv("F_URL", "http://module-f:8006/generate")
VIDEO_AUTO_ENABLED = os.getenv("VIDEO_AUTO_ENABLED", "false").lower() == "true"

# ── 并发锁：防止多个管道同时运行导致竞争条件 ──
_pipeline_lock = asyncio.Lock()
_last_pipeline_end = 0  # epoch seconds
PIPELINE_COOLDOWN = 10  # 两次管道运行之间最少间隔秒数


def _error_detail(e: Exception, resp: httpx.Response | None = None) -> str:
    """Extract meaningful error message, including response body if available."""
    msg = str(e)
    if resp is not None:
        try:
            body = resp.text[:500]
            if body and body != msg:
                msg = f"{msg} | body: {body}"
        except Exception:
            pass
    return msg


async def _compute_hours_back(pool, type_: str) -> int:
    """计算抓取时间窗口。

    早报：固定 24 小时。
    晚报：动态计算 — 从最近一次早报生成时间到现在的小时差，
          确保只拉早报之后发布的新内容。未找到早报时回退到 12 小时。
    """
    if type_ == "morning":
        return 24

    # 晚报：以最近一次早报生成时间为起点
    row = await pool.fetchrow(
        "SELECT generated_at FROM briefings WHERE type='morning' ORDER BY generated_at DESC LIMIT 1"
    )
    if row and row["generated_at"]:
        morning_at = row["generated_at"]
        # 确保有时区信息（数据库可能返回 naive datetime）
        if morning_at.tzinfo is None:
            morning_at = morning_at.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - morning_at
        hours = int(delta.total_seconds() / 3600) + 1  # +1 小时缓冲，避免边界漏抓
        # 安全钳：最少24小时（保证晚报有足够内容），最多48小时
        hours = max(24, min(48, hours))
        logger.info(
            "Evening hours_back=%dh (morning generated at %s, %dh ago)",
            hours,
            morning_at.strftime("%H:%M"),
            int(delta.total_seconds() / 3600),
        )
        return hours

    # 回退：无早报记录时用默认12小时
    logger.info("Evening hours_back=12 (no morning briefing found, using default)")
    return 12


async def execute_pipeline(type_: str, filter_tags: list[str] | None = None, gen_date: str | None = None,
                      search_keywords: list[str] | None = None) -> dict:
    """Execute full pipeline A -> B -> C(+D optional), write run_log entries.

    Uses a global lock to prevent concurrent pipeline runs from corrupting
    the DB or overwhelming module B (which can't handle parallel requests).
    """
    global _last_pipeline_end

    # 等待锁 + 冷却期
    async with _pipeline_lock:
        elapsed = time.time() - _last_pipeline_end
        if elapsed < PIPELINE_COOLDOWN:
            wait = PIPELINE_COOLDOWN - elapsed
            logger.info(f"Pipeline cooldown: waiting {wait:.1f}s before next run")
            await asyncio.sleep(wait)

        result = await _execute_pipeline_impl(type_, filter_tags, gen_date, search_keywords)
        _last_pipeline_end = time.time()
        return result


async def _execute_pipeline_impl(type_: str, filter_tags: list[str] | None, gen_date: str | None,
                                  search_keywords: list[str] | None = None) -> dict:
    """Internal implementation (caller must hold _pipeline_lock)."""
    batch_id = str(uuid.uuid4())
    today = gen_date if gen_date else date.today().isoformat()
    pool = get_pool()

    steps = {}

    async def log_step(module: str, status: str, detail: dict | None = None):
        step_id = str(uuid.uuid4())
        is_finished = status != "running"
        await pool.execute(
            """INSERT INTO run_log (id, module, run_type, status, started_at, finished_at, detail)
               VALUES ($1, $2, $3, $4, now(),
                       CASE WHEN $5::boolean THEN now() ELSE NULL END,
                       COALESCE($6::jsonb, '{}'))""",
            uuid.UUID(step_id), module, type_, status, is_finished,
            json.dumps(detail) if detail else None,
        )
        return step_id

    # Step 1: A - fetch (timeout 180s — RSS scraping can be slow)
    await log_step("A", "running")
    async with httpx.AsyncClient(timeout=180) as client:
        hours = await _compute_hours_back(pool, type_)
        r = None
        try:
            a_payload: dict = {"batch_id": batch_id, "hours_back": hours}
            if search_keywords:
                a_payload["search_keywords"] = search_keywords
            r = await client.post(A_URL, json=a_payload)
            r.raise_for_status()
            steps["fetch"] = r.json()
            await log_step("A", "success", steps["fetch"])
        except Exception as e:
            err = _error_detail(e, r)
            steps["fetch"] = {"status": "failed", "error": err}
            await log_step("A", "failed", steps["fetch"])
            return {"status": "failed", "batch_id": batch_id, "type": type_, "steps": steps}

        # Step 2: B - AI process (timeout 300s — LLM calls are slow, allow retries)
        await log_step("B", "running")
        briefing_id = None

        b_payload: dict = {"type": type_, "date": today, "batch_id": batch_id}
        if filter_tags:
            b_payload["tags"] = filter_tags

        b_success = False
        last_b_error = ""
        for attempt in range(3):
            if attempt > 0:
                wait_s = attempt * 5
                logger.warning(f"Module B retry {attempt}/3 after {wait_s}s...")
                await asyncio.sleep(wait_s)
            r = None
            try:
                r = await client.post(B_URL, json=b_payload, timeout=300)
                r.raise_for_status()
                steps["process"] = r.json()
                briefing_id = steps["process"].get("briefing_id")
                if briefing_id:
                    b_success = True
                    await log_step("B", "success", steps["process"])
                    break
                else:
                    last_b_error = f"B returned no briefing_id: {r.text[:300]}"
                    logger.warning(last_b_error)
            except Exception as e:
                last_b_error = _error_detail(e, r)
                logger.error(f"Module B attempt {attempt+1}/3 failed: {last_b_error}")

        if not b_success:
            steps["process"] = {"status": "failed", "error": last_b_error or "unknown B error"}
            await log_step("B", "failed", steps["process"])
            return {"status": "failed", "batch_id": batch_id, "type": type_, "steps": steps}

        # Auto-trigger video generation (both morning and evening, fire-and-forget)
        if b_success and VIDEO_AUTO_ENABLED:
            asyncio.create_task(_trigger_video_async(batch_id))

        # Step 3: C (push) + D (publish, optional — 本地通常不启动)
        if not briefing_id:
            return {"status": "failed", "batch_id": batch_id, "type": type_, "steps": steps,
                    "error": "no briefing_id from B"}

        await log_step("C", "running")

        # 尝试调用 D，但 D 不可用不阻塞主流程
        d_available = await _check_url(client, D_URL) if D_URL else False
        if d_available:
            await log_step("D", "running")
            c_result, d_result = await asyncio.gather(
                _do_push(client, briefing_id),
                _do_publish(client, briefing_id),
                return_exceptions=True,
            )
        else:
            logger.info("Module D not available — skipping publish step (non-critical)")
            c_result = await _do_push(client, briefing_id)
            d_result = None
            steps["publish"] = {"status": "skipped", "reason": "Module D not running (optional)"}
            await log_step("D", "success", {"skipped": True, "reason": "D not available"})

        for module, result in [("C", c_result), ("D", d_result)]:
            step_key = "push" if module == "C" else "publish"
            if module == "D" and d_result is None:
                continue  # already recorded as skipped
            if isinstance(result, Exception):
                steps[step_key] = {"status": "failed", "error": str(result)}
                await log_step(module, "failed", {"error": str(result)})
            else:
                steps[step_key] = result
                await log_step(module, "success", result)

    return {
        "status": "ok",
        "batch_id": batch_id,
        "type": type_,
        "briefing_id": briefing_id,
        "steps": steps,
    }


def _service_health_url(url: str) -> str:
    """Derive health-check URL from a service base URL."""
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "/health", "", "", ""))


async def _check_url(client: httpx.AsyncClient, url: str) -> bool:
    """Quick check if a service is reachable."""
    try:
        health_url = _service_health_url(url)
        r = await client.get(health_url, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


async def _do_push(client, briefing_id: str) -> dict:
    r = await client.post(C_URL, json={"briefing_id": briefing_id})
    r.raise_for_status()
    return r.json()


async def _do_publish(client, briefing_id: str) -> dict:
    r = await client.post(D_URL, json={"briefing_id": briefing_id})
    r.raise_for_status()
    return r.json()


async def _trigger_video_async(batch_id: str):
    """Fire-and-forget: trigger video generation then auto-publish to Douyin.

    Polls module-f for completion, then publishes the vertical version to Douyin.
    Failures at any stage do NOT affect the main document pipeline.
    """
    try:
        result = await execute_video_pipeline()
        logger.info(f"Video auto-triggered for batch {batch_id}: status={result.get('status')}")
        video_id = result.get("video_id") or result.get("module_f_response", {}).get("video_id", "")

        if not video_id:
            logger.warning("No video_id in response, skipping Douyin auto-publish")
            return

        # Poll for video completion (background, non-blocking to pipeline)
        asyncio.create_task(_poll_and_publish_douyin(video_id))
    except Exception as e:
        logger.error(f"Video auto-trigger failed (non-blocking): {e}")


async def _poll_and_publish_douyin(video_id: str):
    """Poll module-f until video is done, then publish to Douyin via module-d HTTP API."""
    if not os.getenv("DOUYIN_AUTO_PUBLISH", "false").lower() == "true":
        logger.info("[Douyin] DOUYIN_AUTO_PUBLISH=false, skipping auto-publish")
        return

    F_STATUS_URL = os.getenv("F_URL", "http://module-f:8006").rstrip("/") + f"/status/{video_id}"
    D_VIDEO_URL = os.getenv("D_URL", "http://module-d:8004").rstrip("/") + "/publish-video"

    # Poll with backoff
    poll_delays = [15, 30, 60, 60, 60, 60, 60, 60, 60, 60]  # ~8 min total
    for delay in poll_delays:
        await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(F_STATUS_URL)
                r.raise_for_status()
                status = r.json()
        except Exception as e:
            logger.warning("[Douyin] Status poll failed: %s", e)
            continue

        state = status.get("status", "")
        if state == "done":
            logger.info("[Douyin] Video %s generation complete, triggering Douyin publish...", video_id)

            meta = status.get("metadata") or {}
            vertical_path = meta.get("vertical_path", "")
            cover_path = meta.get("cover_path", "")
            title = status.get("title", "AI早报")

            if not vertical_path:
                logger.warning("[Douyin] No vertical_path in metadata, skipping")
                return

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.post(D_VIDEO_URL, json={
                        "video_path": vertical_path,
                        "title": title,
                        "tags": ["AI", "人工智能", "科技", "AI早报"],
                        "cover_path": cover_path if cover_path else "",
                    })
                    r.raise_for_status()
                    result = r.json()
                    logger.info("[Douyin] Publish result: %s", result)
            except Exception as e:
                logger.error("[Douyin] Publish HTTP call failed: %s", e)
            return

        elif state == "failed":
            logger.error("[Douyin] Video %s generation failed: %s", video_id, status.get("error_msg", ""))
            return

        logger.info("[Douyin] Video %s still processing (%s), waiting %ds...", video_id, state, delay)

    logger.warning("[Douyin] Video %s polling timed out after ~8 min", video_id)


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
