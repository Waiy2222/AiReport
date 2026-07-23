"""七步管道串联 — 读 raw_items → AI 加工 → 配图 → 写 briefings"""
import json
import uuid
import logging
import asyncpg
from datetime import datetime, timezone, timedelta

from ai.analyzer import batch_score
from ai.dedup import url_dedup, semantic_dedup
from ai.enricher import enrich
from ai.summarizer import summarize
from ai.image_matcher import match_images_for_briefing
from ai.debate_agent import run_debate
from ai.client import get_client, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)
SCORE_THRESHOLD = 6  # 提高门槛：低质内容不再混入
MAX_AGE_HOURS = 36   # 发布时间超过此值的新闻直接拒绝（保证当天/前一天）


def _parse_metadata(it: dict) -> dict:
    """安全解析 metadata 字段：处理 None / 缺失 / JSON 字符串三种情况。

    解析后缓存回 it['metadata']，避免同一 item 反复解析 JSON 字符串。
    """
    meta = it.get("metadata")
    if meta is None:
        it["metadata"] = {}
        return {}
    if isinstance(meta, str):
        try:
            parsed = json.loads(meta)
            it["metadata"] = parsed  # 缓存回 dict，后续调用直接命中
            return parsed
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse metadata JSON string for item: %s", it.get("title", "?"))
            it["metadata"] = {}
            return {}
    if isinstance(meta, dict):
        return meta
    it["metadata"] = {}
    return {}


def _get_ai_score(it: dict) -> float:
    """安全获取 ai_score：优先从 metadata 取，其次从 item 直接字段"""
    meta = _parse_metadata(it)
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            meta = {}
    if not isinstance(meta, dict):
        meta = {}
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
        existing = await conn.fetchrow(
            "SELECT id FROM briefings WHERE type=$1 AND date=$2 AND language='zh'",
            briefing_type, briefing_date,
        )
        # BUG-004 fix: 如果评分阶段有数据（passed>0）但最终 sections 为空，
        # 说明摘要失败，仍需更新 DB 让用户看到"摘要生成中"而非过时数据
        if existing and stats.get("passed", 0) == 0:
            return existing["id"]
        # passed>0 但 final_count=0 → 摘要失败，创建新记录或用原文兜底
        if stats.get("passed", 0) > 0:
            merged_stats["draft_mode"] = True  # 标记为草稿（摘要在后续重试中补全）

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
        json.dumps(briefing.get("tl_dr", []), ensure_ascii=False),
        json.dumps(briefing.get("sections", []), ensure_ascii=False),
        json.dumps(briefing.get("key_takeaways", []), ensure_ascii=False),
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


def _attach_debate_to_briefing(briefing: dict, source_items: list[dict]) -> None:
    """将原始 items 的 debate 数据映射回 LLM 生成的 briefing sections 中。

    匹配策略：先按 url 精确匹配，再按 title 前缀匹配（LLM 可能会改写标题）。
    """
    # 构建 source items 的 debate 查找表: {url: debate, title_prefix: debate}
    url_debate_map = {}
    title_debate_map = {}
    for it in source_items:
        meta = _parse_metadata(it)
        debate = meta.get("debate")
        if not debate:
            continue
        url = it.get("url", "")
        title = it.get("title", "")
        if url:
            url_debate_map[url] = debate
        if title:
            # 取前 20 个字符做模糊匹配
            title_debate_map[title[:20]] = debate

    for section in briefing.get("sections", []):
        for item in section.get("items", []):
            # 精确 URL 匹配
            item_url = item.get("url", "")
            if item_url and item_url in url_debate_map:
                item["debate"] = url_debate_map[item_url]
                continue

            # 模糊 title 匹配
            item_title = item.get("title", "")
            if item_title:
                for prefix, debate in title_debate_map.items():
                    if item_title[:15] == prefix[:15]:
                        item["debate"] = debate
                        break


def _is_english(text: str) -> bool:
    """判断文本是否主要为英文（中文字符 < 5%）"""
    if not text:
        return False
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    alpha_chars = sum(1 for c in text if c.isalpha() and ord(c) < 128)
    total = chinese_chars + alpha_chars
    if total == 0:
        return False
    return chinese_chars / total < 0.05


def _get_published_at(it: dict) -> datetime | None:
    """从 item 提取 published_at，处理多种类型（date/str/None）"""
    val = it.get("published_at")
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val)
        except (ValueError, TypeError):
            return None
    return None


def _clean_text(text: str) -> str:
    """清理文本：HTML实体 → 繁体→简体 → 去多余空格"""
    if not text:
        return ""
    import html as _html
    import re as _re
    text = _html.unescape(text)  # &nbsp; &amp; &#XXXX;
    try:
        from zhconv import convert
        text = convert(text, "zh-cn")
    except Exception:
        pass
    text = _re.sub(r"\s+", " ", text)
    return text.strip()


async def _translate_items(items: list[dict]) -> list[dict]:
    """将英文标题/摘要翻译为中文，保持已有中文不变。批量并发翻译（每批5条）。"""
    for it in items:
        it["title"] = _clean_text(it.get("title", ""))
        if it.get("content"):
            it["content"] = _clean_text(it["content"])
    need_translation = []
    for it in items:
        title = it.get("title", "")
        if _is_english(title):
            need_translation.append(it)

    if not need_translation:
        return items

    logger.info("Translating %d English items to Chinese (batched)", len(need_translation))

    client = get_client()
    TRANSLATION_SYSTEM = (
        "你是专业翻译。将以下英文科技新闻翻译为简体中文，保持原意。"
        "专有名词用中文惯用译名（Claude→克劳德、Google→谷歌、Microsoft→微软、"
        "Apple→苹果、NVIDIA→英伟达、OpenAI→OpenAI、NBA→NBA）。"
        "无通用译名时保留英文。"
        "输出JSON数组，每条对应输入: [{\"title_cn\":\"中文标题\",\"summary_cn\":\"中文摘要(50字内)\"}]"
    )

    BATCH_SIZE = 5
    for batch_start in range(0, len(need_translation), BATCH_SIZE):
        batch = need_translation[batch_start:batch_start + BATCH_SIZE]
        try:
            # 构建批量输入
            lines = []
            for i, it in enumerate(batch):
                title = it["title"][:200]
                content = (it.get("content") or "")[:300]
                lines.append(f"[{i}] Title: {title}\nContent: {content}")
            batch_text = "\n\n".join(lines)

            resp = await client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": TRANSLATION_SYSTEM},
                    {"role": "user", "content": batch_text},
                ],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            raw = (resp.choices[0].message.content or "").strip()
            # 修复 LLM 偶尔返回单引号 JSON 的问题
            if raw.startswith("{'") or raw.startswith("[{"):
                raw = raw.replace("'", '"')
            result = json.loads(raw)

            # 兼容两种返回格式: {"translations": [...]} 或 [...]
            translations = result if isinstance(result, list) else result.get("translations", [])
            for i, trans in enumerate(translations):
                if i >= len(batch):
                    break
                cn_title = (trans.get("title_cn") or "").strip()
                cn_summary = (trans.get("summary_cn") or "").strip()
                if cn_title:
                    batch[i]["title_cn"] = cn_title
                    batch[i]["title"] = cn_title
                if cn_summary:
                    batch[i]["content"] = cn_summary
        except Exception as e:
            logger.warning("Batch translation failed for %d items: %s",
                           len(batch), str(e)[:100])
            # 回退：逐个翻译
            for it in batch:
                try:
                    await _translate_single(client, it)
                except Exception:
                    pass

    return items


async def _translate_single(client, it: dict) -> None:
    """单条翻译回退（批量失败时使用）。"""
    title = it["title"][:200]
    content = (it.get("content") or "")[:300]
    text = f"Title: {title}\nContent: {content}"
    resp = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{
            "role": "system",
            "content": "你是专业翻译。将英文科技新闻翻译为简体中文，保持原意。输出JSON: {\"title_cn\":\"中文标题\",\"summary_cn\":\"中文摘要(50字内)\"}",
        }, {
            "role": "user",
            "content": text,
        }],
        temperature=0.3,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    raw = (resp.choices[0].message.content or "").strip()
    if raw.startswith("{'"):
        raw = raw.replace("'", '"')
    result = json.loads(raw)
    cn_title = (result.get("title_cn") or "").strip()
    cn_summary = (result.get("summary_cn") or "").strip()
    if cn_title:
        it["title_cn"] = cn_title
        it["title"] = cn_title
    if cn_summary:
        it["content"] = cn_summary


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
        # 同步 metadata 中的 tags 到 item 顶层（debate/summarizer 依赖 it["tags"]）
        meta = _parse_metadata(it)
        if not it.get("tags") and meta.get("tags"):
            it["tags"] = meta["tags"]
    stats["scored"] = len(items)

    # ②.⑤ Phase 3: AI 辩论 — 对高分新闻跑 3 个 Agent 多维度分析（失败不回退）
    try:
        # 确保所有 item 的 metadata 是 dict（辩论函数依赖 dict 操作）
        for it in items:
            meta = it.get("metadata")
            if isinstance(meta, str):
                try:
                    it["metadata"] = json.loads(meta)
                except Exception:
                    it["metadata"] = {}
            elif not isinstance(meta, dict):
                it["metadata"] = {}
        items = await run_debate(items)
    except Exception as e:
        logger.warning("Debate step failed (non-blocking): %s", e)

    # ③ 过滤低分 (threshold >= SCORE_THRESHOLD)
    passed = [it for it in items if it.get("ai_score", 0) >= SCORE_THRESHOLD]
    stats["passed"] = len(passed)

    if not passed:
        async with pool.acquire() as conn:
            briefing_id = await _insert_briefing(conn, briefing_type, briefing_date, {"tl_dr": [], "sections": [], "key_takeaways": []}, stats)
        return {"briefing_id": briefing_id, "stats": stats, "briefing": {}}

    # ③.⑤ 时效性门禁：优先当天/前一天新闻，不足时逐步放宽
    # 多级回退：36h → 48h → 72h，保证至少 MIN_FRESH_ITEMS 条新闻
    MIN_FRESH_ITEMS = 8
    AGENCY_FALLBACKS = [36, 48, 72]  # 小时
    now = datetime.now(timezone.utc)

    fresh_passed = None
    used_age_hours = AGENCY_FALLBACKS[0]
    for age_hours in AGENCY_FALLBACKS:
        age_cutoff = now - timedelta(hours=age_hours)
        fresh_passed = [
            it for it in passed
            if _get_published_at(it) is None or _get_published_at(it) >= age_cutoff
        ]
        used_age_hours = age_hours
        if len(fresh_passed) >= MIN_FRESH_ITEMS:
            break
        logger.info("Freshness: only %d items within %dh, relaxing to %dh",
                     len(fresh_passed), age_hours,
                     AGENCY_FALLBACKS[AGENCY_FALLBACKS.index(age_hours) + 1]
                     if age_hours != AGENCY_FALLBACKS[-1] else age_hours)

    stats["aged_out"] = len(passed) - len(fresh_passed)
    stats["freshness_hours"] = used_age_hours
    if stats["aged_out"] > 0:
        logger.info("Freshness gate: removed %d items older than %dh (%d remain)",
                     stats["aged_out"], used_age_hours, len(fresh_passed))
    passed = fresh_passed

    if not passed:
        async with pool.acquire() as conn:
            briefing_id = await _insert_briefing(conn, briefing_type, briefing_date, {"tl_dr": [], "sections": [], "key_takeaways": []}, stats)
        return {"briefing_id": briefing_id, "stats": stats, "briefing": {}}

    # ④ URL 精确去重
    before_url = len(passed)
    passed = url_dedup(passed)
    stats["dedup_url_removed"] = before_url - len(passed)

    # ④.⑤ 跨天去重：检查所有近期简报（同类型+异类型+同日异时段）最近2天已用的URL
    # 晚报放宽：只去重前几天的URL，不去重当天早报的URL（允许与早报内容重叠）
    cross_dedup_removed = 0
    try:
        async with pool.acquire() as conn:
            if briefing_type == "evening":
                existing_urls = await conn.fetch(
                    """SELECT DISTINCT jsonb_array_elements_text(
                           COALESCE(raw_stats->'urls', '[]'::jsonb)
                       ) AS url
                       FROM briefings
                       WHERE date >= $1::date - INTERVAL '2 days'
                         AND date < $1::date""",
                    briefing_date,
                )
            else:
                existing_urls = await conn.fetch(
                    """SELECT DISTINCT jsonb_array_elements_text(
                           COALESCE(raw_stats->'urls', '[]'::jsonb)
                       ) AS url
                       FROM briefings
                       WHERE (date = $1::date AND type != $2)
                          OR (date >= $1::date - INTERVAL '2 days'
                              AND date < $1::date)""",
                    briefing_date, briefing_type,
                )
            seen_urls = {r["url"] for r in existing_urls if r["url"]}
            if seen_urls:
                before_cross = len(passed)
                passed = [it for it in passed if it.get("url", "") not in seen_urls]
                cross_dedup_removed = before_cross - len(passed)
                if cross_dedup_removed:
                    logger.info("Cross-day dedup: removed %d items already in recent briefings (last 2 days)",
                                cross_dedup_removed)
    except Exception as e:
        logger.warning("Cross-day dedup skipped: %s", e)
    stats["cross_dedup_removed"] = cross_dedup_removed

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

    # ⑦.⑤ 翻译英文内容为中文
    passed = await _translate_items(passed)

    # ⑧ 摘要 + 标签生成（V2: 含 headline + image_keywords）
    briefing = await summarize(passed, briefing_type)

    # ⑧.⑤ Phase 3: 将辩论数据映射回 LLM 生成的 briefing items（按 URL/title 匹配）
    _attach_debate_to_briefing(briefing, passed)

    # ⑨ 配图匹配（为 sections 中每条 item 匹配 image_url）
    briefing = await match_images_for_briefing(briefing)

    # ⑨.⑤ LLM 摘要后兜底过滤
    if filter_tags:
        briefing = _filter_by_tags(briefing, filter_tags)

    stats["final_count"] = sum(len(s.get("items", [])) for s in briefing.get("sections", []))

    # 存储所有 URL 供跨简报去重
    stats["urls"] = [it.get("url", "") for s in briefing.get("sections", []) for it in s.get("items", []) if it.get("url")]

    # ⑩ 写入 briefings 表（upsert 防重复，headline 存入 raw_stats）
    async with pool.acquire() as conn:
        briefing_id = await _insert_briefing(conn, briefing_type, briefing_date, briefing, stats)

    return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}


# ══════════════════════════════════════════════════════════════════
# 个性化简报轻量版流水线
# ══════════════════════════════════════════════════════════════════


async def run_personalized_pipeline(
    pool: asyncpg.Pool,
    briefing_type: str,
    briefing_date: str,
    filter_tags: list[str],
    openid: str,
    interest_text: str,
    interest_tags: list[str],
    passed_items: list[dict],
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

    # AI 语义去重
    before_semantic = len(passed)
    passed = await semantic_dedup(passed)
    stats["dedup_semantic_removed"] = before_semantic - len(passed)

    # 标签预过滤（仅当 items 有标签时才执行，否则靠摘要器后过滤）
    if filter_tags:
        has_tags = any(
            bool((_parse_metadata(it) or {}).get("tags"))
            for it in passed
        )
        if has_tags:
            passed = _filter_items_by_tags(passed, filter_tags)
        else:
            logger.info("No item-level tags found, skipping pre-filter, "
                        "relying on summarizer post-filter")

    if not passed:
        async with pool.acquire() as conn:
            briefing = {"tl_dr": [], "sections": [], "key_takeaways": []}
            briefing_id = await _insert_personalized_briefing(
                conn, briefing_type, briefing_date, briefing, stats,
                openid=openid, interest_text=interest_text, interest_tags=interest_tags,
            )
        return {"briefing_id": briefing_id, "stats": stats, "briefing": briefing}

    # 翻译
    passed = await _translate_items(passed)

    # 摘要 + 标签生成（核心，保留）
    briefing = await summarize(passed, briefing_type)

    # LLM 摘要后兜底过滤
    if filter_tags:
        briefing = _filter_by_tags(briefing, filter_tags)

    # 配图匹配
    briefing = await match_images_for_briefing(briefing)

    stats["final_count"] = sum(len(s.get("items", [])) for s in briefing.get("sections", []))
    stats["urls"] = [it.get("url", "") for s in briefing.get("sections", []) for it in s.get("items", []) if it.get("url")]

    # 写入 briefings 表（带个性化标记，仅 INSERT 不做 upsert）
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
) -> uuid.UUID:
    """写入个性化简报 — 仅 INSERT（不做 upsert），每次生成都是新记录"""
    import uuid as _uuid_mod
    from datetime import date as _date_type
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

    await conn.execute(
        """INSERT INTO briefings (id, type, date, language, tl_dr, sections, key_takeaways, raw_stats,
           requested_by, interest_text, interest_tags, is_personalized)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, true)""",
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
    return briefing_id
