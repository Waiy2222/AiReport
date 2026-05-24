"""七步管道串联 — 读 raw_items → AI 加工 → 写 briefings"""
import json
import uuid
import asyncpg

from ai.analyzer import batch_score
from ai.dedup import url_dedup, semantic_dedup
from ai.enricher import enrich
from ai.summarizer import summarize

SCORE_THRESHOLD = 6


async def read_raw_items(pool: asyncpg.Pool, batch_id: uuid.UUID) -> list[dict]:
    """① 从 raw_items 读取指定 batch 的数据"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, source, title, url, content, author, published_at, metadata, batch_id "
            "FROM raw_items WHERE batch_id = $1",
            batch_id,
        )
    return [dict(r) for r in rows]


async def run_pipeline(pool: asyncpg.Pool, briefing_type: str, briefing_date: str, batch_id: uuid.UUID) -> dict:
    """执行完整 AI 加工流水线，返回 briefing_id 和统计信息"""
    stats = {
        "fetched": 0,
        "scored": 0,
        "passed": 0,
        "dedup_url_removed": 0,
        "dedup_semantic_removed": 0,
        "final_count": 0,
    }

    # ① 读取 raw_items
    items = await read_raw_items(pool, batch_id)
    stats["fetched"] = len(items)
    if not items:
        briefing_id = uuid.uuid4()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO briefings (id, type, date, tl_dr, sections, key_takeaways, raw_stats) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                briefing_id, briefing_type, briefing_date, "[]", "[]", "[]", json.dumps(stats),
            )
        return {"briefing_id": briefing_id, "stats": stats}

    # ② AI 评分
    items = await batch_score(items)
    stats["scored"] = len(items)

    # ③ 过滤低分 (threshold >= 6)
    passed = [it for it in items if it.get("ai_score", 0) >= SCORE_THRESHOLD]
    stats["passed"] = len(passed)

    if not passed:
        briefing_id = uuid.uuid4()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO briefings (id, type, date, tl_dr, sections, key_takeaways, raw_stats) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                briefing_id, briefing_type, briefing_date, "[]", "[]", "[]", json.dumps(stats),
            )
        return {"briefing_id": briefing_id, "stats": stats}

    # ④ URL 精确去重
    before_url = len(passed)
    passed = url_dedup(passed)
    stats["dedup_url_removed"] = before_url - len(passed)

    # ⑤ AI 语义去重
    before_semantic = len(passed)
    passed = await semantic_dedup(passed)
    stats["dedup_semantic_removed"] = before_semantic - len(passed)

    # ⑥ 背景补充
    passed = await enrich(passed)

    # ⑦ 摘要 + 标签生成
    briefing = await summarize(passed, briefing_type)
    stats["final_count"] = len(passed)

    # ⑧ 写入 briefings 表
    briefing_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO briefings (id, type, date, tl_dr, sections, key_takeaways, raw_stats) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            briefing_id,
            briefing_type,
            briefing_date,
            json.dumps(briefing.get("tl_dr", []), ensure_ascii=False),
            json.dumps(briefing.get("sections", []), ensure_ascii=False),
            json.dumps(briefing.get("key_takeaways", []), ensure_ascii=False),
            json.dumps(stats, ensure_ascii=False),
        )

    return {"briefing_id": briefing_id, "stats": stats}
