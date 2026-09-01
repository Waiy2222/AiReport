"""个性化简报轻量版流水线 — 跳过 AI评分/辩论/补充，预计30-45秒。

与 pipeline.run_pipeline 的区别：
- 不调用 batch_score（复用现有 ai_score）
- 不调用 run_debate（三Agent辩论，耗时大户）
- 不调用 enrich（LLM 背景补充）
- 不做跨天去重（专属简报独立去重池）
"""
import asyncio
import json
import uuid as _uuid_mod
import logging
from datetime import datetime, timezone, timedelta, date as _date_type

import asyncpg

from ai.dedup import url_dedup, semantic_dedup
from ai.summarizer import summarize
from ai.image_matcher import match_images_for_briefing

# 共享工具函数（保留在 pipeline.py 中，通过 import 引用）
from pipeline import (
    _parse_metadata,
    _get_published_at,
    _filter_items_by_tags,
    _translate_items,
    _filter_by_tags,
)

logger = logging.getLogger(__name__)


async def run_personalized_pipeline(
    pool: asyncpg.Pool,
    briefing_type: str,
    briefing_date: str,
    filter_tags: list[str],
    openid: str,
    interest_text: str,
    interest_tags: list[str],
    passed_items: list[dict],
    search_keywords: list[str] | None = None,
) -> dict:
    """轻量版专属简报流水线 — 跳过 AI评分/辩论/补充，预计30-45秒。

    与 run_pipeline 的区别：
    - 不调用 batch_score（复用现有 ai_score）
    - 不调用 run_debate（三Agent辩论，耗时大户）
    - 不调用 enrich（LLM 背景补充）
    - 不做跨天去重（专属简报独立去重池）
    """
    stats = {
        "fetched": len(passed_items),
        "passed": len(passed_items),
        "dedup_url_removed": 0,
        "dedup_semantic_removed": 0,
        "aged_out": 0,
        "final_count": 0,
        "personalized": True,
        "interest_tags": interest_tags,
    }

    if not passed_items:
        async with pool.acquire() as conn:
            briefing = {"tl_dr": [], "sections": [], "key_takeaways": []}
            briefing_id = await _insert_personalized_briefing(
                conn, briefing_type, briefing_date, briefing, stats,
                openid=openid, interest_text=interest_text, interest_tags=interest_tags,
            )
        return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}

    now = datetime.now(timezone.utc)
    MIN_FRESH_ITEMS = 8
    AGENCY_FALLBACKS = [36, 48, 72]
    fresh_passed = None
    used_age_hours = AGENCY_FALLBACKS[0]
    for age_hours in AGENCY_FALLBACKS:
        age_cutoff = now - timedelta(hours=age_hours)
        fresh_passed = [
            it for it in passed_items
            if _get_published_at(it) is None or _get_published_at(it) >= age_cutoff
        ]
        used_age_hours = age_hours
        if len(fresh_passed) >= MIN_FRESH_ITEMS:
            break
    stats["aged_out"] = len(passed_items) - len(fresh_passed)
    stats["freshness_hours"] = used_age_hours
    passed = fresh_passed

    if not passed:
        async with pool.acquire() as conn:
            briefing = {"tl_dr": [], "sections": [], "key_takeaways": []}
            briefing_id = await _insert_personalized_briefing(
                conn, briefing_type, briefing_date, briefing, stats,
                openid=openid, interest_text=interest_text, interest_tags=interest_tags,
            )
        return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}

    # URL 精确去重
    before_url = len(passed)
    passed = url_dedup(passed)
    stats["dedup_url_removed"] = before_url - len(passed)

    # 语义去重：仅在 >20 条时启用，且超时 8 秒快速跳过
    if len(passed) > 20:
        try:
            before_semantic = len(passed)
            passed = await asyncio.wait_for(semantic_dedup(passed), timeout=8.0)
            stats["dedup_semantic_removed"] = before_semantic - len(passed)
        except asyncio.TimeoutError:
            logger.info("Semantic dedup timed out, skipping")
            stats["dedup_semantic_removed"] = 0
    else:
        stats["dedup_semantic_removed"] = 0

    # 标签预过滤：仅当超过半数 item 已有标签时才执行过滤
    # 个性化简报常有 Google News 动态搜索结果（无标签），此时跳过预过滤
    if filter_tags:
        def _safe_meta_tags(it):
            meta = _parse_metadata(it)
            if not isinstance(meta, dict):
                return None
            return meta.get("tags")
        tagged_count = sum(1 for it in passed if bool(_safe_meta_tags(it)))
        # 超过半数有标签 → 常规 RSS 数据，执行过滤
        if tagged_count > len(passed) * 0.5:
            passed = _filter_items_by_tags(passed, filter_tags)
        else:
            logger.info("Majority of items lack tags (likely dynamic search), "
                        "skipping pre-filter (tagged=%d/%d)", tagged_count, len(passed))

    if not passed:
        async with pool.acquire() as conn:
            briefing = {"tl_dr": [], "sections": [], "key_takeaways": []}
            briefing_id = await _insert_personalized_briefing(
                conn, briefing_type, briefing_date, briefing, stats,
                openid=openid, interest_text=interest_text, interest_tags=interest_tags,
            )
        return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}

    # 翻译：个性化简报抓取结果已是中文，跳过
    # passed = await _translate_items(passed)

    # 个性化简报：搜索来源优先 + 常规内容降权，确保用户兴趣匹配
    boost_keywords = (search_keywords or []) + (interest_tags or [])
    if boost_keywords or interest_text:
        boosted = 0
        penalized = 0
        for it in passed:
            title = (it.get("title", "") + " " + (it.get("content") or "")).lower()
            current = it.get("ai_score", 5) or 5
            boost = 0.0

            # ① Google News 动态搜索来源：大幅加分到 8 分起步
            meta = _parse_metadata(it)
            is_search_result = bool(meta.get("search_keyword") or it.get("source") == "news_search")
            if is_search_result:
                current = max(current, 8.0)  # 确保搜索内容不低于常规高分内容
                boosted += 1

            # ② 常规 RSS 内容降权（个性化简报中非搜索来源不应占主导）
            if not is_search_result and search_keywords:
                current = current - 2.0  # 常规 RSS 降 2 分
                penalized += 1

            # ③ 标题/内容含兴趣关键词的额外加分
            for kw in boost_keywords:
                if kw.lower() in title:
                    boost += 0.5
            # 中文 2-gram 匹配
            if interest_text:
                text_chars = interest_text.replace(" ", "")
                for i in range(len(text_chars) - 1):
                    bigram = text_chars[i:i+2]
                    if len(bigram) >= 2 and bigram in title:
                        boost += 0.3

            it["ai_score"] = max(0, min(10, current + boost))

        if boosted or penalized:
            logger.info("Score adjust: %d search boosted, %d RSS penalized (keywords=%s)",
                        boosted, penalized, boost_keywords[:3])

    # 摘要 + 标签生成（先按分数截断到60条，保证速度 <60s）
    MAX_SUMMARIZE_ITEMS = 60
    if len(passed) > MAX_SUMMARIZE_ITEMS:
        passed.sort(key=lambda it: it.get("ai_score", 5) or 5, reverse=True)
        passed = passed[:MAX_SUMMARIZE_ITEMS]
        logger.info("Truncated to top %d items for summarization", MAX_SUMMARIZE_ITEMS)
    briefing = await summarize(passed, briefing_type,
                               interest_tags=interest_tags,
                               interest_text=interest_text)

    # LLM 摘要后兜底过滤（仅当 filter_tags 覆盖核心标签时执行，个性化简报跳过）
    if filter_tags and len(filter_tags) < 10:
        # 少量标签 = 个性化简报，放宽过滤：保留所有内容，最后由 summarizer 质量把关
        logger.info("Personalized briefing: skipping post-filter (filter_tags=%s)", filter_tags)
    elif filter_tags:
        briefing = _filter_by_tags(briefing, filter_tags)

    # 配图匹配：并发请求（asyncio.gather），5s 总超时
    briefing = await match_images_for_briefing(briefing, interest_tags=interest_tags)

    stats["final_count"] = sum(len(s.get("items", [])) for s in briefing.get("sections", []))
    stats["urls"] = [it.get("url", "") for s in briefing.get("sections", []) for it in s.get("items", []) if it.get("url")]

    # 写入 briefings 表（带个性化标记）
    async with pool.acquire() as conn:
        briefing_id = await _insert_personalized_briefing(
            conn, briefing_type, briefing_date, briefing, stats,
            openid=openid, interest_text=interest_text, interest_tags=interest_tags,
        )

    return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}


async def _insert_personalized_briefing(
    conn,
    briefing_type: str,
    briefing_date: str,
    briefing: dict,
    stats: dict,
    openid: str,
    interest_text: str,
    interest_tags: list[str],
) -> _uuid_mod.UUID:
    """写入个性化简报 — upsert 防重复，每次生成覆盖旧记录"""
    briefing_id = _uuid_mod.uuid4()
    headline = briefing.get("headline", {})
    merged_stats = dict(stats)
    if headline:
        merged_stats["headline"] = headline

    # asyncpg 需要 date 对象，不能传字符串
    briefing_date_obj = _date_type.fromisoformat(briefing_date)

    # 为每个用户的专属简报生成唯一 language 值，避免 (type,date,language) 约束冲突
    # VARCHAR(5), 格式: 'zp' + 用户hash后3位
    _lang_suffix = str(hash(openid) % 1000).zfill(3)
    _personalized_lang = f'zp{_lang_suffix}'

    actual_id = await conn.fetchval(
        """INSERT INTO briefings (id, type, date, language, tl_dr, sections, key_takeaways, raw_stats,
           requested_by, interest_text, interest_tags, is_personalized)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, true)
           ON CONFLICT (type, date, language) DO UPDATE SET
             tl_dr = EXCLUDED.tl_dr,
             sections = EXCLUDED.sections,
             key_takeaways = EXCLUDED.key_takeaways,
             raw_stats = EXCLUDED.raw_stats,
             interest_text = EXCLUDED.interest_text,
             interest_tags = EXCLUDED.interest_tags,
             generated_at = now()
           RETURNING id""",
        briefing_id,
        briefing_type,
        briefing_date_obj,
        _personalized_lang,
        json.dumps(briefing.get("tl_dr", []), ensure_ascii=False),
        json.dumps(briefing.get("sections", []), ensure_ascii=False),
        json.dumps(briefing.get("key_takeaways", []), ensure_ascii=False),
        json.dumps(merged_stats, ensure_ascii=False),
        openid,
        interest_text,
        json.dumps(interest_tags, ensure_ascii=False),
    )
    return actual_id
