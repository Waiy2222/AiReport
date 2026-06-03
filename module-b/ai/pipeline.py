"""Module B — 7-step AI content processing pipeline.

Supports both DeepSeek API and mock fallback when no API key is configured.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DeepSeek configuration
# ---------------------------------------------------------------------------
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"


def _has_api_key() -> bool:
    return bool(DEEPSEEK_API_KEY and DEEPSEEK_API_KEY.startswith("sk-"))


def _get_openai_client():
    if not _has_api_key():
        return None
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


async def _llm_chat(messages: list[dict], temperature: float = 0.7,
                    max_tokens: int = 4096) -> str | None:
    """Single LLM call.  Returns content string or None on failure."""
    client = _get_openai_client()
    if client is None:
        return None
    try:
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content
    except Exception:
        logger.warning("LLM call failed", exc_info=True)
        return None


def _extract_json(text: str) -> str:
    """Extract a pure JSON substring from a possibly markdown-wrapped response.

    Handles cases where the model wraps JSON in ```json blocks or adds
    explanatory text before/after the JSON payload.
    """
    import re
    t = text.strip()

    # Try stripping ``` fences first
    if "```" in t:
        # Extract content between the first pair of ``` fences
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", t, re.DOTALL)
        if m:
            return m.group(1).strip()

    # If the text starts with { or [, try to find the matching close
    if t and t[0] in ("{", "["):
        # Try simple truncation of trailing backticks
        if t.endswith("```"):
            t = t[:-3].strip()
        return t

    # Last resort: find the first JSON object/array in the text
    for prefix in ("{", "["):
        idx = t.find(prefix)
        if idx >= 0:
            # Find matching close brace/bracket
            close = "}" if prefix == "{" else "]"
            depth = 0
            end = idx
            for j, ch in enumerate(t[idx:], start=idx):
                if ch == prefix:
                    depth += 1
                elif ch == close:
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
            if depth == 0:
                return t[idx:end].strip()

    return t


# ===================================================================
# Public entry point — runs the full 7-step pipeline
# ===================================================================


async def run_pipeline(
    pool: asyncpg.Pool,
    batch_id: str,
    briefing_type: str,
    briefing_date: date,
) -> dict[str, Any]:
    """Execute the 7-step pipeline and return result dictionary.

    Returns a dict with ``briefing_id`` (str), ``stats`` (dict), ``status`` (str).
    """
    stats: dict[str, int] = {
        "fetched": 0,
        "scored": 0,
        "passed": 0,
        "dedup_removed": 0,
        "final_count": 0,
    }

    # ---- Step 1: Fetch ---------------------------------------------------
    items = await _step_fetch(pool, batch_id)
    stats["fetched"] = len(items)
    logger.info("Step 1 (fetch): %d items", len(items))

    if not items:
        return _empty_result(stats, "no raw_items found for batch")

    # ---- Step 2: Score ---------------------------------------------------
    items = await _step_score(pool, items)
    stats["scored"] = sum(1 for it in items if _safe_meta(it).get("ai_score") is not None)
    logger.info("Step 2 (score): %d scored", stats["scored"])

    # ---- Step 3: Filter --------------------------------------------------
    items, _ = await _step_filter(items, threshold=6)
    stats["passed"] = len(items)
    logger.info("Step 3 (filter): %d passed threshold", stats["passed"])

    if not items:
        return _empty_result(stats, "all items filtered out")

    # ---- Step 4: Dedup ---------------------------------------------------
    items, removed = await _step_dedup(items)
    stats["dedup_removed"] = removed
    logger.info("Step 4 (dedup): %d removed, %d remain", removed, len(items))

    if not items:
        return _empty_result(stats, "all items removed by dedup")

    # ---- Step 5: Enrich --------------------------------------------------
    items = await _step_enrich(items)
    logger.info("Step 5 (enrich): enriched %d items", len(items))

    # ---- Step 6: Generate briefing ---------------------------------------
    briefing_json = await _step_generate(items, briefing_type, briefing_date)
    logger.info("Step 6 (generate): tl_dr=%d, sections=%d, key_takeaways=%d",
                len(briefing_json.get("tl_dr", [])),
                len(briefing_json.get("sections", [])),
                len(briefing_json.get("key_takeaways", [])))

    # ---- Step 7: Save ----------------------------------------------------
    briefing_id = await _step_save(pool, briefing_type, briefing_date,
                                   briefing_json, stats)
    stats["final_count"] = len(items)
    logger.info("Step 7 (save): briefing_id=%s", briefing_id)

    return {
        "status": "ok",
        "briefing_id": briefing_id,
        "stats": stats,
    }


def _empty_result(stats: dict, reason: str) -> dict:
    logger.warning("Pipeline early exit: %s", reason)
    import uuid
    return {
        "status": "ok",
        "briefing_id": str(uuid.uuid4()),
        "stats": stats,
    }


# ===================================================================
# Step 1 — Fetch
# ===================================================================

async def _step_fetch(pool: asyncpg.Pool, batch_id: str) -> list[dict]:
    rows = await pool.fetch(
        """SELECT id, source, title, url, content, author,
                  published_at, metadata, batch_id
           FROM raw_items
           WHERE batch_id = $1
           ORDER BY published_at DESC""",
        batch_id,
    )
    items: list[dict] = []
    for r in rows:
        meta = r["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        items.append({
            "id": str(r["id"]),
            "source": r["source"],
            "title": r["title"],
            "url": r["url"],
            "content": r["content"] or "",
            "author": r["author"],
            "published_at": r["published_at"].isoformat() if r["published_at"] else None,
            "metadata": meta or {},
            "batch_id": str(r["batch_id"]),
        })
    return items


# ===================================================================
# Step 2 — Score
# ===================================================================

_SCORE_BATCH = 5


async def _step_score(pool: asyncpg.Pool, items: list[dict]) -> list[dict]:
    if not items:
        return items

    # Ensure every item has a proper metadata dict
    for it in items:
        it["metadata"] = _safe_meta(it)

    if _has_api_key():
        await _score_via_api(items)
    else:
        for it in items:
            it["metadata"]["ai_score"] = _mock_score_one(it)

    # Persist updated metadata
    for it in items:
        if "ai_score" in it["metadata"]:
            await pool.execute(
                "UPDATE raw_items SET metadata = $1::jsonb WHERE id = $2::uuid",
                json.dumps(it["metadata"], ensure_ascii=False),
                it["id"],
            )
    return items


async def _score_via_api(items: list[dict]) -> None:
    for i in range(0, len(items), _SCORE_BATCH):
        batch = items[i:i + _SCORE_BATCH]
        prompt = _build_score_prompt(batch)
        result = await _llm_chat([
            {"role": "system",
             "content": "你是一个专业的AI资讯编辑，擅长评估资讯的重要性和相关性。始终以JSON格式回复，不要包含markdown代码块。"},
            {"role": "user", "content": prompt},
        ], temperature=0.3, max_tokens=1000)

        if result is None:
            for it in batch:
                it["metadata"]["ai_score"] = _mock_score_one(it)
            continue

        try:
            scores = json.loads(_extract_json(result))
            for entry in scores:
                idx = int(entry.get("index", 0))
                if 0 <= idx < len(batch):
                    batch[idx]["metadata"]["ai_score"] = float(entry.get("score", 5))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            logger.warning("Score parsing failed, using mock for batch")
            for it in batch:
                it["metadata"]["ai_score"] = _mock_score_one(it)


def _build_score_prompt(batch: list[dict]) -> str:
    lines = []
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    for idx, it in enumerate(batch):
        # 计算新闻距今多久
        age_str = ""
        pub = it.get("published_at")
        if pub:
            try:
                if isinstance(pub, str):
                    pub = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                age_hours = (now - pub.astimezone(timezone.utc)).total_seconds() / 3600
                if age_hours < 24:
                    age_str = f"（{int(age_hours)}小时前发布）"
                else:
                    age_str = f"（{int(age_hours/24)}天前发布）"
            except Exception:
                pass
        lines.append(
            f"[{idx}] 标题: {it['title']}\n"
            f"    来源: {it['source']}\n"
            f"    发布时间: {age_str}\n"
            f"    内容: {it['content'][:300]}"
        )
    joined = "\n\n".join(lines)
    return (
        "请对以下每条AI资讯的相关性和时效性打分(1-10)。\n"
        "评分标准（不偏向任何单一领域，各领域平等对待）：\n"
        "10分=当日重大突破/头部事件/重磅发布（不限领域：科技、体育、时政、财经均可）;\n"
        "8-9分=近2日重要动态/知名公司/开源发布/赛事结果/政策出台;\n"
        "6-7分=有价值的行业资讯/技术讨论/赛事预告/产业动态;\n"
        "4-5分=一般内容或超过3天旧闻;\n"
        "1-3分=关联弱或超过1周旧闻。\n"
        "⏰ 时效性是第一权重：3天前扣2分，5天前扣4分，7天以上不超过3分。\n"
        "领域多样性与AI核心同等重要。\n\n"
        f"以JSON数组格式返回：[{{\"index\":0,\"score\":8.5}}, ...]\n\n"
        f"{joined}"
    )


def _mock_score_one(item: dict) -> float:
    """Heuristic scoring when no API key is available."""
    from datetime import datetime, timezone
    combined = (item.get("title", "") + " " + item.get("content", "")).lower()
    score = 5.0

    # 时效惩罚：检查发布时间
    pub = item.get("published_at")
    if pub:
        try:
            if isinstance(pub, str):
                pub = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - pub.astimezone(timezone.utc)).total_seconds() / 3600
            if age_hours > 72:   # 3天以上
                score -= 2
            if age_hours > 120:  # 5天以上
                score -= 4
            if age_hours > 168:  # 7天以上
                score -= 6
        except Exception:
            pass

    # High-signal keywords (all domains)
    for kw in ["发布", "开源", "release", "launch", "正式", "突破",
               "超越", "夺冠", "决赛", "上市", "签署", "出台", "突破",
               "v0.", "v1.", "v2.", "v3.", "v4.", "v5."]:
        if kw.lower() in combined:
            score += 0.5

    # Important entities (AI + 体育 + 科技 + 时政)
    for ent in ["deepseek", "openai", "gpt", "claude", "gemini", "llama",
                "meta", "google", "anthropic", "langchain", "agent",
                "rag", "vllm", "huggingface", "qwen", "通义", "文心",
                "nba", "espn", "库里", "詹姆斯", "欧冠", "英超", "lpl",
                "欧盟", "白宫", "国务院", "商务部", "央行",
                "苹果", "特斯拉", "华为", "字节", "腾讯", "阿里"]:
        if ent in combined:
            score += 0.5

    # Source bonus (broadened)
    if item.get("source") in ("github", "hackernews", "espn", "cnbc", "techcrunch", "36氪"):
        score += 0.5

    return round(max(1.0, min(10.0, score)), 1)


# ===================================================================
# Step 3 — Filter
# ===================================================================

def _safe_meta(it: dict) -> dict:
    """安全获取 metadata 字典：处理 None / 缺失 / JSON 字符串"""
    meta = it.get("metadata")
    if meta is None:
        return {}
    if isinstance(meta, str):
        try:
            return json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(meta, dict):
        return meta
    return {}


async def _step_filter(items: list[dict], threshold: float = 5.5) -> tuple[list[dict], list[dict]]:
    passed: list[dict] = []
    removed: list[dict] = []
    for it in items:
        s = _safe_meta(it).get("ai_score", 0)
        if isinstance(s, (int, float)) and s >= threshold:
            passed.append(it)
        else:
            removed.append(it)
    return passed, removed


# ===================================================================
# Step 4 — Deduplicate
# ===================================================================

async def _step_dedup(items: list[dict]) -> tuple[list[dict], int]:
    if not items:
        return items, 0
    if _has_api_key() and len(items) >= 3:
        return await _dedup_via_api(items)
    return _dedup_heuristic(items)


async def _dedup_via_api(items: list[dict]) -> tuple[list[dict], int]:
    lines = []
    for idx, it in enumerate(items):
        lines.append(
            f"[{idx}] 标题: {it['title']}\n"
            f"    来源: {it['source']}\n"
            f"    内容: {it['content'][:200]}"
        )
    prompt = (
        "严格识别以下资讯中的重复条目，返回所有应删除的索引数组。\n"
        "重复包括：同一事件不同媒体报道、同一产品不同角度、同一场比赛不同来源。\n"
        "保留评分最高/信息最丰富的一条，删除其余。\n"
        "以JSON数组格式返回如 [1,5,7]。没有重复则返回 []。\n\n"
        + "\n\n".join(lines)
    )
    result = await _llm_chat([
        {"role": "system",
         "content": "你是AI资讯编辑专家。只以JSON数组回复，不要markdown代码块。"},
        {"role": "user", "content": prompt},
    ], temperature=0.1, max_tokens=500)

    if result is None:
        return items, 0

    try:
        to_remove = json.loads(_extract_json(result))
        if isinstance(to_remove, list):
            remove_set = {int(x) for x in to_remove if isinstance(x, (int, float))}
            kept = [it for idx, it in enumerate(items) if idx not in remove_set]
            return kept, len(items) - len(kept)
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Dedup parsing failed, keeping all items")
    return items, 0


def _dedup_heuristic(items: list[dict]) -> tuple[list[dict], int]:
    """Simple Jaccard-based dedup on title tokens (no API)."""
    kept: list[dict] = []
    removed = 0
    seen_token_sets: list[set[str]] = []

    for it in items:
        tokens = set(it["title"].lower().split())
        is_dup = False
        for seen in seen_token_sets:
            if not tokens or not seen:
                continue
            overlap = len(tokens & seen)
            union = len(tokens | seen)
            if overlap / union > 0.35:  # more than 35% overlap → duplicate
                is_dup = True
                break
        if is_dup:
            removed += 1
        else:
            kept.append(it)
            seen_token_sets.append(tokens)

    return kept, removed


# ===================================================================
# Step 5 — Enrich
# ===================================================================

async def _step_enrich(items: list[dict]) -> list[dict]:
    if not items:
        return items
    # Ensure metadata is a proper dict (belt-and-suspenders after _step_score)
    for it in items:
        it["metadata"] = _safe_meta(it)
    if _has_api_key():
        await _enrich_via_api(items)
    else:
        for it in items:
            it["metadata"]["background"] = _mock_enrich_one(it)
    return items


async def _enrich_via_api(items: list[dict]) -> None:
    for i in range(0, len(items), _SCORE_BATCH):
        batch = items[i:i + _SCORE_BATCH]
        lines = []
        for idx, it in enumerate(batch):
            lines.append(
                f"[{idx}] 标题: {it['title']}\n"
                f"    来源: {it['source']}\n"
                f"    内容: {it['content'][:300]}"
            )
        prompt = (
            "为以下每条AI资讯生成1-2句中文背景补充，帮助读者理解其意义，"
            "以JSON数组格式返回：[{\"index\":0,\"background\":\"...\"}, ...]\n\n"
            + "\n\n".join(lines)
        )
        result = await _llm_chat([
            {"role": "system",
             "content": "你是AI行业分析师。只以JSON数组回复，不要markdown代码块。"},
            {"role": "user", "content": prompt},
        ], temperature=0.5, max_tokens=2000)

        if result is None:
            for it in batch:
                it["metadata"]["background"] = _mock_enrich_one(it)
            continue

        try:
            enrichments = json.loads(_extract_json(result))
            for entry in enrichments:
                idx = int(entry.get("index", 0))
                if 0 <= idx < len(batch):
                    batch[idx]["metadata"]["background"] = entry.get("background", "")
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            for it in batch:
                it["metadata"]["background"] = _mock_enrich_one(it)


def _mock_enrich_one(item: dict) -> str:
    source = item.get("source", "")
    if source == "github":
        return (f"来自GitHub的开源项目动态，由{item.get('author') or '社区'}维护，"
                "反映了AI开源生态的最新进展。")
    if source == "hackernews":
        return "Hacker News社区热门讨论，反映了全球开发者对AI技术的最新关注点和趋势判断。"
    if source == "rss":
        return "来自科技媒体/AI公司官方博客的资讯，是了解AI行业动态的重要渠道。"
    return f"来自{source}的AI相关资讯。"


# ===================================================================
# Step 6 — Generate briefing
# ===================================================================

async def _step_generate(
    items: list[dict],
    briefing_type: str,
    briefing_date: date,
) -> dict[str, Any]:
    if _has_api_key() and items:
        result = await _generate_via_api(items, briefing_type, briefing_date)
        if result is not None:
            return result
    return _generate_mock(items, briefing_type, briefing_date)


async def _generate_via_api(
    items: list[dict],
    briefing_type: str,
    briefing_date: date,
) -> dict | None:
    lines = []
    for idx, it in enumerate(items):
        score = _safe_meta(it).get("ai_score", "N/A")
        bg = _safe_meta(it).get("background", "")
        lines.append(
            f"[{idx}] 标题: {it['title']}\n"
            f"    来源: {it['source']}\n"
            f"    评分: {score}\n"
            f"    内容: {it['content'][:300]}\n"
            f"    背景: {bg}\n"
            f"    URL: {it['url']}"
        )
    type_label = "早报" if briefing_type == "morning" else "晚报"
    prompt = (
        f"你是AI资讯编辑。基于以下{len(items)}条资讯生成{type_label}。\n"
        f"日期：{briefing_date.isoformat()}\n\n"
        "请以严格的JSON格式返回（不要markdown代码块），包含三个字段：\n"
        "1. tl_dr: 5-10条核心要点（中文一句话概括）\n"
        "2. sections: 按主题分组的章节数组（5-8个章节），每个章节含 title 和 items。"
        "每个item含 title, summary(50-100字中文), score(数字), url, source, tags(2-4个中文标签数组)\n"
        "3. key_takeaways: 3-5条关键洞察（中文）\n\n"
        "重要：请覆盖以下标签类别，每个类别至少1条："
        "LLM、Agent、开源、基础设施、多模态、AI编程、AI产品、AI安全、AI政策、融资、体育、时事、科技、工具、政策。"
        "未覆盖类别的酌情扣分。\n\n"
        "信息如下：\n\n" + "\n\n".join(lines) + "\n\n"
        "请直接返回JSON对象：{\"tl_dr\":[...], \"sections\":[...], \"key_takeaways\":[...]}"
    )
    result = await _llm_chat([
        {"role": "system",
         "content": "你是专业AI资讯编辑，将纷杂资讯整理为结构化简报。只返回JSON对象，不要markdown。"},
        {"role": "user", "content": prompt},
    ], temperature=0.7, max_tokens=8192)

    if result is None:
        return None

    try:
        data = json.loads(_extract_json(result))
        if isinstance(data, dict) and "tl_dr" in data and "sections" in data:
            return data
    except (json.JSONDecodeError, KeyError):
        logger.warning("Briefing generation JSON parsing failed")
    return None


def _generate_mock(
    items: list[dict],
    briefing_type: str,
    briefing_date: date,
) -> dict[str, Any]:
    """Deterministic mock briefing generator — no API required."""
    return {
        "tl_dr": _mock_tldr(items),
        "sections": _mock_sections(items),
        "key_takeaways": _mock_key_takeaways(items, briefing_type),
    }


def _mock_tldr(items: list[dict]) -> list[str]:
    ranked = sorted(items,
                    key=lambda x: _safe_meta(x).get("ai_score", 0),
                    reverse=True)
    result: list[str] = []
    for it in ranked[:10]:
        title = it["title"]
        result.append(title if len(title) <= 80 else title[:77] + "...")
    return result


# Topic keyword mapping for auto-classification
_TOPIC_MAP: list[tuple[str, list[str]]] = [
    ("大模型与开源", [
        "llama", "deepseek", "gpt", "qwen", "claude", "gemini", "开源",
        "openai", "meta", "google", "anthropic", "通义", "百川", "chatglm",
        "llm", "大模型", "模型", "transformer",
    ]),
    ("Agent与智能体", [
        "agent", "crewai", "autogpt", "智能体", "自主", "agentic",
    ]),
    ("AI工具链与基础设施", [
        "vllm", "chromadb", "ragflow", "langfuse", "langchain", "dify",
        "promptflow", "transformers", "huggingface", "mcp", "tool",
        "框架", "sdk", "推理", "检索", "向量", "可观测",
    ]),
    ("AI编程与开发", [
        "代码", "编程", "copilot", "cursor", "ide", "审查", "next.js",
        "windsurf", "开发",
    ]),
    ("AI政策与行业动态", [
        "欧盟", "法案", "监管", "白皮书", "政策", "信通院", "斯坦福",
        "融资", "指数", "ai index", "合规",
    ]),
]


def _classify_item(item: dict) -> str:
    combined = (item["title"] + " " + item["content"]).lower()
    for section_title, keywords in _TOPIC_MAP:
        if any(kw.lower() in combined for kw in keywords):
            return section_title
    return "其他AI资讯"


def _mock_sections(items: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for it in items:
        section = _classify_item(it)
        grouped.setdefault(section, []).append(it)

    sections: list[dict] = []
    for title, section_items in grouped.items():
        items_list: list[dict] = []
        for it in section_items:
            items_list.append({
                "title": it["title"],
                "summary": it["content"][:100] if it["content"] else it["title"],
                "score": _safe_meta(it).get("ai_score", 5),
                "url": it["url"],
                "source": it["source"],
                "tags": _extract_tags(it),
            })
        sections.append({"title": title, "items": items_list})
    return sections


_TAG_KEYWORDS: list[tuple[str, list[str]]] = [
    ("LLM", ["llm", "大模型", "gpt", "claude", "gemini", "deepseek", "llama",
             "qwen", "通义", "百川"]),
    ("开源", ["开源", "open source", "mit", "apache", "github", "release"]),
    ("Agent", ["agent", "智能体", "自主"]),
    ("推理", ["推理", "inference", "r1", "reasoning"]),
    ("RAG", ["rag", "检索增强"]),
    ("MCP", ["mcp", "model context protocol"]),
    ("工具", ["tool", "工具", "sdk", "框架", "framework", "平台"]),
    ("政策", ["监管", "法案", "政策", "合规", "欧盟"]),
    ("多模态", ["多模态", "multimodal", "vision"]),
    ("编程", ["代码", "编程", "coding", "copilot", "ide"]),
    ("基础设施", ["基础设施", "infrastructure", "部署"]),
    ("融资", ["融资", "yc", "投资", "估值", "初创"]),
]


def _extract_tags(item: dict) -> list[str]:
    combined = (item["title"] + " " + item["content"]).lower()
    tags: list[str] = []
    for tag, keywords in _TAG_KEYWORDS:
        if any(kw.lower() in combined for kw in keywords):
            tags.append(tag)
            if len(tags) >= 4:
                break
    return tags[:4]


def _mock_key_takeaways(items: list[dict],
                        briefing_type: str) -> list[str]:
    n = len(items)
    type_label = "早报" if briefing_type == "morning" else "晚报"
    takeaways = [
        f"本期AI{type_label}收录{n}条高质量资讯，涵盖大模型、Agent框架、AI基础设施等多个领域，反映了AI行业的快速迭代趋势。",
        "开源大模型生态持续活跃，Llama、DeepSeek、Qwen等模型持续缩小与闭源模型的差距。",
        "AI Agent和智能体框架成为行业热点，多Agent协作与自主Agent能力受到广泛关注。",
    ]
    return takeaways


# ===================================================================
# Step 7 — Save
# ===================================================================

async def _step_save(
    pool: asyncpg.Pool,
    briefing_type: str,
    briefing_date: date,
    briefing_json: dict[str, Any],
    stats: dict[str, int],
) -> str:
    import uuid as _uuid
    briefing_uuid = _uuid.uuid4()
    briefing_id = str(briefing_uuid)

    # Ensure key_takeaways is never None
    key_takeaways = briefing_json.get("key_takeaways") or []

    row_id = await pool.fetchval(
        """INSERT INTO briefings (id, type, date, language, tl_dr, sections,
                                  key_takeaways, raw_stats)
           VALUES ($1::uuid, $2, $3, 'zh', $4::jsonb, $5::jsonb, $6::jsonb,
                   $7::jsonb)
           ON CONFLICT (type, date, language) DO UPDATE SET
             tl_dr = EXCLUDED.tl_dr,
             sections = EXCLUDED.sections,
             key_takeaways = EXCLUDED.key_takeaways,
             raw_stats = EXCLUDED.raw_stats
           RETURNING id""",
        briefing_uuid,
        briefing_type,
        briefing_date,
        json.dumps(briefing_json.get("tl_dr", []), ensure_ascii=False),
        json.dumps(briefing_json.get("sections", []), ensure_ascii=False),
        json.dumps(key_takeaways, ensure_ascii=False),
        json.dumps(stats, ensure_ascii=False),
    )
    return str(row_id)
