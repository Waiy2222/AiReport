"""Dashboard API routes — richer stats, logs, retry, and multi-module health."""
import uuid
import json
import logging
from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Query

from db import get_pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _get_pool_or_503():
    try:
        return get_pool()
    except RuntimeError:
        raise HTTPException(503, "database not initialized")

MODULE_HEALTH_URLS = {
    "A": "http://module-a:8001/health",
    "B": "http://module-b:8002/health",
    "C": "http://module-c:8003/health",
    "D": "http://module-d:8004/health",
    "F": "http://module-f:8006/health",
}


# ---------------------------------------------------------------------------
#  Aggregate stats
# ---------------------------------------------------------------------------
@router.get("/stats")
async def dashboard_stats():
    """Aggregate stats: briefings by type, success rate by module,
    daily trends (7 / 30 days), average pipeline duration."""
    pool = _get_pool_or_503()

    # -- briefings by type --
    briefing_rows = await pool.fetch(
        "SELECT type, COUNT(*) AS cnt FROM briefings GROUP BY type"
    )
    briefings_by_type = {r["type"]: r["cnt"] for r in briefing_rows}
    total_briefings = sum(briefings_by_type.values())

    # -- success / failed by module --
    module_stats = {}
    for m in ["A", "B", "C", "D", "F"]:
        total = await pool.fetchval(
            "SELECT COUNT(*) FROM run_log WHERE module=$1", m)
        ok = await pool.fetchval(
            "SELECT COUNT(*) FROM run_log WHERE module=$1 AND status='success'", m)
        fail = await pool.fetchval(
            "SELECT COUNT(*) FROM run_log WHERE module=$1 AND status='failed'", m)
        module_stats[m] = {
            "total": total,
            "success": ok,
            "failed": fail,
            "success_rate": round(ok / total * 100, 1) if total > 0 else 0,
        }

    # -- daily trends (7 days, detailed) --
    today = date.today()
    daily_7 = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        runs = await pool.fetchval(
            "SELECT COUNT(*) FROM run_log WHERE started_at::date = $1", d)
        briefs = await pool.fetchval(
            "SELECT COUNT(*) FROM briefings WHERE date = $1", d)
        daily_7.append({"date": d.isoformat(), "runs": runs, "briefings": briefs})

    # -- daily trends (30 days, aggregated) --
    daily_30 = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        runs = await pool.fetchval(
            "SELECT COUNT(*) FROM run_log WHERE started_at::date = $1", d)
        if runs > 0:
            daily_30.append({"date": d.isoformat(), "runs": runs})

    # -- average pipeline duration by run_type --
    avg_duration = {}
    for rt in ["morning", "evening"]:
        rows = await pool.fetch(
            """SELECT module,
                      AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) AS avg_sec
               FROM run_log
               WHERE run_type=$1
                 AND finished_at IS NOT NULL
                 AND started_at IS NOT NULL
               GROUP BY module""",
            rt,
        )
        avg_duration[rt] = {
            r["module"]: round(r["avg_sec"], 1) if r["avg_sec"] else 0
            for r in rows
        }

    # -- grand totals --
    total_runs = await pool.fetchval("SELECT COUNT(*) FROM run_log")
    total_success = await pool.fetchval(
        "SELECT COUNT(*) FROM run_log WHERE status='success'")
    total_failed = await pool.fetchval(
        "SELECT COUNT(*) FROM run_log WHERE status='failed'")

    return {
        "briefings_by_type": briefings_by_type,
        "total_briefings": total_briefings,
        "module_stats": module_stats,
        "daily_trends_7": daily_7,
        "daily_trends_30": daily_30,
        "avg_duration_by_type": avg_duration,
        "overall": {
            "total_runs": total_runs,
            "total_success": total_success,
            "total_failed": total_failed,
            "success_rate": round(total_success / total_runs * 100, 1)
            if total_runs > 0 else 0,
        },
    }


# ---------------------------------------------------------------------------
#  Filtered run logs with pagination
# ---------------------------------------------------------------------------
@router.get("/logs")
async def dashboard_logs(
    module: str = Query(None, description="Filter: A | B | C | D | E"),
    run_type: str = Query(None, description="Filter: morning | evening"),
    status: str = Query(None, description="Filter: success | failed | running"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Paginated, filterable run_log entries."""
    pool = _get_pool_or_503()

    conditions = []
    params = []
    idx = 1

    if module:
        conditions.append(f"module=${idx}")
        params.append(module)
        idx += 1
    if run_type:
        conditions.append(f"run_type=${idx}")
        params.append(run_type)
        idx += 1
    if status:
        conditions.append(f"status=${idx}")
        params.append(status)
        idx += 1

    where = " AND ".join(conditions) if conditions else "TRUE"

    total = await pool.fetchval(
        f"SELECT COUNT(*) FROM run_log WHERE {where}", *params)

    params.extend([limit, offset])
    rows = await pool.fetch(
        f"""SELECT id, module, run_type, status, started_at, finished_at, detail
            FROM run_log
            WHERE {where}
            ORDER BY started_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}""",
        *params,
    )

    def _detail(row_detail):
        if isinstance(row_detail, str):
            try:
                return json.loads(row_detail)
            except (json.JSONDecodeError, TypeError):
                return row_detail
        return row_detail

    logs = [
        {
            "id": str(r["id"]),
            "module": r["module"],
            "run_type": r["run_type"],
            "status": r["status"],
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
            "detail": _detail(r.get("detail")),
        }
        for r in rows
    ]

    return {"total": total, "limit": limit, "offset": offset, "logs": logs}


# ---------------------------------------------------------------------------
#  Retry a failed pipeline step
# ---------------------------------------------------------------------------
@router.post("/retry/{run_id}")
async def retry_pipeline(run_id: str):
    """Re-run the full pipeline for the same type as the failed run."""
    pool = _get_pool_or_503()

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, "Invalid run_id UUID format")

    row = await pool.fetchrow(
        "SELECT module, run_type, status FROM run_log WHERE id=$1", run_uuid)
    if not row:
        raise HTTPException(404, "Run log entry not found")
    if row["status"] != "failed":
        raise HTTPException(
            400, f"Can only retry failed runs (current status: {row['status']})")

    run_type = row["run_type"]
    logger.info(f"Retrying failed run {run_id} (type={run_type})")

    from pipeline import execute_pipeline

    try:
        result = await execute_pipeline(run_type)
        return {
            "status": "retry_completed",
            "run_id": run_id,
            "run_type": run_type,
            "result": result,
        }
    except Exception as e:
        logger.error(f"Retry failed for {run_id}: {e}")
        raise HTTPException(500, f"Retry execution failed: {e}")


# ---------------------------------------------------------------------------
#  Health of all modules
# ---------------------------------------------------------------------------
@router.get("/health/all")
async def health_all():
    """Health status of modules A-E via run_log + optional HTTP probes."""
    pool = _get_pool_or_503()

    modules = {}
    for m in ["A", "B", "C", "D", "E", "F"]:
        row = await pool.fetchrow(
            "SELECT status, started_at FROM run_log WHERE module=$1 "
            "ORDER BY started_at DESC LIMIT 1",
            m,
        )
        modules[m] = {
            "status": row["status"] if row else "unknown",
            "last_run": row["started_at"].isoformat()
            if row and row["started_at"] else None,
            "http_health": None,
        }

    # Best-effort HTTP probes (short timeout)
    async with httpx.AsyncClient(timeout=3) as client:
        for mod_name, url in MODULE_HEALTH_URLS.items():
            try:
                r = await client.get(url)
                modules[mod_name]["http_health"] = (
                    "ok" if r.status_code == 200 else f"status_{r.status_code}")
            except Exception as exc:
                modules[mod_name]["http_health"] = f"unreachable"

    # DB check
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "modules": modules,
        "db": db_status,
        "timestamp": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
#  User behavior stats
# ---------------------------------------------------------------------------
@router.get("/users/stats")
async def user_behavior_stats():
    """Aggregate user behavior: tag distribution, active users, recent activity."""
    pool = _get_pool_or_503()

    # Active users (any behavior in last 7 days)
    active_7d = await pool.fetchval(
        """SELECT COUNT(DISTINCT user_openid) FROM user_behavior
           WHERE created_at > NOW() - INTERVAL '7 days'""")

    # Active users (last 30 days)
    active_30d = await pool.fetchval(
        """SELECT COUNT(DISTINCT user_openid) FROM user_behavior
           WHERE created_at > NOW() - INTERVAL '30 days'""")

    # Total users with subscriptions
    total_subscribed = await pool.fetchval(
        "SELECT COUNT(*) FROM subscriptions")

    # Tag distribution — from subscriptions.preferences
    tag_rows = await pool.fetch(
        "SELECT preferences FROM subscriptions WHERE preferences IS NOT NULL")
    tag_counts: dict[str, int] = {}
    for r in tag_rows:
        prefs = r["preferences"]
        if isinstance(prefs, str):
            prefs = json.loads(prefs)
        tags = prefs.get("tags", []) if isinstance(prefs, dict) else []
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1

    # Top actions in last 7 days
    action_counts = {}
    action_rows = await pool.fetch(
        """SELECT action, COUNT(*) AS cnt FROM user_behavior
           WHERE created_at > NOW() - INTERVAL '7 days'
           GROUP BY action""")
    for r in action_rows:
        action_counts[r["action"]] = r["cnt"]

    return {
        "active_users": {
            "last_7_days": active_7d,
            "last_30_days": active_30d,
        },
        "total_subscribed": total_subscribed,
        "tag_distribution": tag_counts,
        "recent_actions": action_counts,
    }


# ---------------------------------------------------------------------------
#  Video status panel
# ---------------------------------------------------------------------------
@router.get("/videos")
async def video_panel(limit: int = Query(10, ge=1, le=50)):
    """Recent videos list with status, duration, and paths."""
    pool = _get_pool_or_503()

    total = await pool.fetchval("SELECT COUNT(*) FROM videos")
    rows = await pool.fetch(
        """SELECT id, type, date, title, status, output_path,
                  duration_seconds, metadata, created_at
           FROM videos ORDER BY created_at DESC LIMIT $1""",
        limit,
    )

    videos = []
    for r in rows:
        meta = r["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        videos.append({
            "id": str(r["id"]),
            "type": r["type"],
            "date": r["date"].isoformat() if r["date"] else None,
            "title": r["title"],
            "status": r["status"],
            "output_path": r["output_path"],
            "duration_seconds": r["duration_seconds"],
            "metadata": meta,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })

    by_status = {}
    status_rows = await pool.fetch(
        "SELECT status, COUNT(*) AS cnt FROM videos GROUP BY status")
    for r in status_rows:
        by_status[r["status"]] = r["cnt"]

    return {
        "total": total,
        "by_status": by_status,
        "videos": videos,
    }
