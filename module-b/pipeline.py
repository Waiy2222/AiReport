"""七步管道串联 — 读 raw_items → AI 加工 → 配图 → 写 briefings"""
import json
import uuid
import logging
import asyncpg

from ai.analyzer import batch_score
from ai.dedup import url_dedup, semantic_dedup
from ai.enricher import enrich
from ai.summarizer import summarize
from ai.image_matcher import match_images_for_briefing

logger = logging.getLogger(__name__)
SCORE_THRESHOLD = 6


def _parse_metadata(it: dict) -> dict:
    """安全解析 metadata 字段：处理 None / 缺失 / JSON 字符串三种情况"""
    meta = it.get("metadata")
    if meta is None:
        return {}
    if isinstance(meta, str):
        try:
            return json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse metadata JSON string for item: %s", it.get("title", "?"))
            return {}
    if isinstance(meta, dict):
        return meta
    return {}


def _get_ai_score(it: dict) -> float:
    """安全获取 ai_score：优先从 metadata 取，其次从 item 直接字段"""
    meta = _parse_metadata(it)
    score = meta.get("ai_score")
    if score is not None:
        return float(score)
    score = it.get("ai_score")
    if score is not None:
        return float(score)
    return 0.0


async def read_raw_items(pool: asyncpg.Pool, batch_id: uuid.UUID) -> list[dict]:
    """① 从 raw_items 读取指定 batch 的数据"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, source, title, url, content, author, published_at, metadata, batch_id "
            "FROM raw_items WHERE batch_id = $1",
            batch_id,
        )
    return [dict(r) for r in rows]


async def _insert_briefing(conn, briefing_type: str, briefing_date: str,
                           briefing: dict, stats: dict) -> uuid.UUID:
    """写入 briefings 表——upsert 处理重复运行，但空数据不覆盖已有有效数据"""
    briefing_id = uuid.uuid4()
    headline = briefing.get("headline", {})
    merged_stats = dict(stats)
    if headline:
        merged_stats["headline"] = headline

    final_count = sum(len(s.get("items", [])) for s in briefing.get("sections", []))

    if final_count == 0:
        # 检查是否已有有效数据，避免空跑覆盖
        existing = await conn.fetchrow(
            "SELECT id FROM briefings WHERE type=$1 AND date=$2 AND language='zh'",
            briefing_type, briefing_date,
        )
        if existing:
            return existing["id"]

    actual_id = await conn.fetchval(
        "INSERT INTO briefings (id, type, date, tl_dr, sections, key_takeaways, raw_stats) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) "
        "ON CONFLICT (type, date, language) DO UPDATE SET "
        "  tl_dr = EXCLUDED.tl_dr, "
        "  sections = EXCLUDED.sections, "
        "  key_takeaways = EXCLUDED.key_takeaways, "
        "  raw_stats = EXCLUDED.raw_stats, "
        "  generated_at = now() "
        "RETURNING id",
        briefing_id,
        briefing_type,
        briefing_date,
        briefing.get("tl_dr", []),
        briefing.get("sections", []),
        briefing.get("key_takeaways", []),
        json.dumps(merged_stats, ensure_ascii=False),
    )
    return actual_id


def _filter_items_by_tags(items: list[dict], filter_tags: list[str]) -> list[dict]:
    """预过滤：在 LLM 摘要前按 mock/LLM 标签过滤 items"""
    if not filter_tags:
        return items
    tag_set = set(filter_tags)
    result = []
    for it in items:
        meta = _parse_metadata(it)
        item_tags = set(meta.get("tags", []))
        if tag_set & item_tags:
            result.append(it)
    return result


def _filter_by_tags(briefing: dict, filter_tags: list[str]) -> dict:
    """LLM 摘要后标签过滤（作为兜底）"""
    if not filter_tags:
        return briefing
    tag_set = set(filter_tags)
    filtered_sections = []
    for section in briefing.get("sections", []):
        filtered_items = [
            item for item in section.get("items", [])
            if tag_set & set(item.get("tags", []))
        ]
        if filtered_items:
            filtered_sections.append({**section, "items": filtered_items})
    briefing["sections"] = filtered_sections
    return briefing


async def run_pipeline(pool: asyncpg.Pool, briefing_type: str, briefing_date: str, batch_id: uuid.UUID, filter_tags: list[str] | None = None) -> dict:
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
        async with pool.acquire() as conn:
            briefing_id = await _insert_briefing(conn, briefing_type, briefing_date, {"tl_dr": [], "sections": [], "key_takeaways": []}, stats)
        return {"briefing_id": briefing_id, "stats": stats, "briefing": {}}

    # ② AI 评分 — 优先使用模块 A 已计算的评分，仅当缺失时才调用 LLM
    need_scoring = [it for it in items if not _get_ai_score(it)]
    if need_scoring:
        scored_batch = await batch_score(need_scoring)
        scored_map = {it["url"]: it.get("ai_score", 5.0) for it in scored_batch}
        for it in items:
            if not _get_ai_score(it):
                meta = _parse_metadata(it)
                new_score = scored_map.get(it["url"], 5.0)
                meta["ai_score"] = new_score
                it["metadata"] = meta
                it["ai_score"] = new_score
    for it in items:
        it["ai_score"] = _get_ai_score(it) or 5.0
    stats["scored"] = len(items)

    # ③ 过滤低分 (threshold >= 6)
    passed = [it for it in items if it.get("ai_score", 0) >= SCORE_THRESHOLD]
    stats["passed"] = len(passed)

    if not passed:
        async with pool.acquire() as conn:
            briefing_id = await _insert_briefing(conn, briefing_type, briefing_date, {"tl_dr": [], "sections": [], "key_takeaways": []}, stats)
        return {"briefing_id": briefing_id, "stats": stats, "briefing": {}}

    # ④ URL 精确去重
    before_url = len(passed)
    passed = url_dedup(passed)
    stats["dedup_url_removed"] = before_url - len(passed)

    # ⑤ AI 语义去重
    before_semantic = len(passed)
    passed = await semantic_dedup(passed)
    stats["dedup_semantic_removed"] = before_semantic - len(passed)

    # ⑥ 标签预过滤（在 LLM 摘要前按 mock/LLM 标签过滤，确保非 AI 内容也能命中）
    if filter_tags:
        passed = _filter_items_by_tags(passed, filter_tags)

    if not passed:
        async with pool.acquire() as conn:
            briefing_id = await _insert_briefing(conn, briefing_type, briefing_date, {"tl_dr": [], "sections": [], "key_takeaways": []}, stats)
        return {"briefing_id": briefing_id, "stats": stats, "briefing": {}}

    # ⑦ 背景补充
    passed = await enrich(passed)

    # ⑧ 摘要 + 标签生成（V2: 含 headline + image_keywords）
    briefing = await summarize(passed, briefing_type)

    # ⑨ 配图匹配（为 sections 中每条 item 匹配 image_url）
    briefing = await match_images_for_briefing(briefing)

    # ⑨.⑤ LLM 摘要后兜底过滤
    if filter_tags:
        briefing = _filter_by_tags(briefing, filter_tags)

    stats["final_count"] = sum(len(s.get("items", [])) for s in briefing.get("sections", []))

    # ⑨ 写入 briefings 表（upsert 防重复，headline 存入 raw_stats）
    async with pool.acquire() as conn:
        briefing_id = await _insert_briefing(conn, briefing_type, briefing_date, briefing, stats)

    return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}
