"""LLM 智能筛选 — 相关性判断 + RAG 上下文 + embedding 生成"""
import json
import logging
import os
import re

import asyncpg

from shared.rag import generate_embeddings_batch, search_similar_items

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DeepSeek configuration
# ---------------------------------------------------------------------------
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"


def _has_api_key() -> bool:
    key = os.getenv("DEEPSEEK_API_KEY", "")
    return bool(key and key.startswith("sk-"))


def _get_client():
    if not _has_api_key():
        return None
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


async def _llm_chat(messages: list[dict], temperature: float = 0.3,
                    max_tokens: int = 2000) -> str | None:
    """单次 LLM 调用，返回 content 或 None"""
    client = _get_client()
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


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """从 LLM 响应提取纯 JSON（处理 ```json 包裹、嵌套、前导文本）"""
    t = text.strip()

    # Try stripping ``` fences
    if "```" in t:
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", t, re.DOTALL)
        if m:
            return m.group(1).strip()

    # If starts with { or [, try to find matching close
    if t and t[0] in ("{", "["):
        if t.endswith("```"):
            t = t[:-3].strip()
        return t

    # Find first JSON object/array in text — pick whichever appears first
    candidates = []
    for prefix in ("{", "["):
        idx = t.find(prefix)
        if idx >= 0:
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
                candidates.append((idx, t[idx:end].strip()))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    return t


# ---------------------------------------------------------------------------
# Mock scoring (no API key fallback)
# ---------------------------------------------------------------------------


def _mock_score_one(item: dict) -> float:
    """启发式评分：不同领域不同评分标准，确保非AI内容也能过线"""
    combined = (item.get("title", "") + " " + item.get("content", "")).lower()
    source = item.get("source", "")
    category = item.get("metadata", {}).get("category", "")

    # 不同领域不同起评分：AI/科技门槛高，体育/时事/国际门槛适中
    if category == "体育" or source == "espn":
        score = 6.5  # 体育起分高，确保过线
    elif category in ("时事", "国际") or source in ("people", "bbc_zh", "voa_zh"):
        score = 6.5  # 时事/国际起分高
    elif category == "科技" or source in ("github", "hackernews", "techcrunch_ai"):
        score = 5.0  # 科技正常起分（AI关键词会加分）
    else:
        score = 5.0

    # 通用热点词
    for kw in ["发布", "开源", "release", "launch", "正式", "突破", "夺冠",
               "政策", "改革", "重大", "紧急", "突发", "官宣", "首发",
               "超越", "v0.", "v1.", "v2.", "v3.", "v4.", "v5."]:
        if kw.lower() in combined:
            score += 0.5

    # 领域关键词加分（每类最多加 2.0）
    ai_bonus = 0
    for ent in ["deepseek", "openai", "gpt", "claude", "gemini", "llama",
                "meta", "google", "anthropic", "langchain", "agent",
                "rag", "mcp", "vllm", "huggingface", "qwen",
                "通义", "文心", "百川", "chatglm", "字节", "华为", "小米"]:
        if ent.lower() in combined:
            ai_bonus += 0.5
    score += min(ai_bonus, 2.0)

    sports_bonus = 0
    for ent in ["nba", "nhl", "mlb", "nfl", "欧冠", "英超", "西甲", "德甲", "意甲",
                "世界杯", "cba", "中超", "梅西", "c罗",
                "奥运会", "世锦赛", "总决赛", "总冠军", "季后赛", "全明星"]:
        if ent.lower() in combined:
            sports_bonus += 0.5
    score += min(sports_bonus, 2.0)

    news_bonus = 0
    for ent in ["国务院", "外交部", "商务部", "央行", "政治局", "两会",
                "拜登", "特朗普", "欧盟", "联合国"]:
        if ent.lower() in combined:
            news_bonus += 0.5
    score += min(news_bonus, 2.0)

    if source in ("github", "hackernews", "xinhua", "people", "cctv_news", "espn"):
        score += 0.5

    return round(max(1.0, min(10.0, score)), 1)


def _mock_tags_one(item: dict) -> list[str]:
    """启发式标签分配"""
    combined = (item.get("title", "") + " " + item.get("content", "")).lower()
    source = item.get("source", "")
    category = item.get("metadata", {}).get("category", "")

    tags = set()

    # Category-based tag
    if category == "科技":
        tags.add("科技")
    elif category == "时事":
        tags.add("时事")
    elif category == "国际":
        tags.add("国际")
    elif category == "体育":
        tags.add("体育")
    # AI/Agent keywords
    for kw in ["deepseek", "openai", "gpt", "claude", "gemini", "llama", "qwen"]:
        if kw in combined:
            tags.add("LLM")
            break
    if "agent" in combined:
        tags.add("Agent")
    if any(kw in combined for kw in ["开源", "open source", "github"]):
        tags.add("开源")
    if any(kw in combined for kw in ["框架", "framework"]):
        tags.add("框架")
    if any(kw in combined for kw in ["工具", "tool", "vllm", "v0."]):
        tags.add("工具")

    # Sports keywords
    if any(kw in combined for kw in ["nba", "nhl", "mlb", "nfl", "cba", "中超"]):
        tags.add("体育")
    if any(kw in combined for kw in ["欧冠", "英超", "西甲", "德甲", "意甲", "世界杯", "欧洲杯"]):
        tags.add("体育")
    if source == "espn":
        tags.add("体育")

    # News/Policy keywords
    if any(kw in combined for kw in ["国务院", "外交部", "商务部", "央行", "政治局", "政策"]):
        tags.add("政策")

    # Finance keywords
    if any(kw in combined for kw in [
        "股票", "股市", "A股", "港股", "美股", "基金", "期货", "债券",
        "融资", "投资", "估值", "IPO", "上市", "市值", "财报",
        "涨停", "跌停", "牛熊", "牛市", "熊市",
        "加息", "降息", "利率", "汇率", "人民币", "美元",
        "证券", "银行", "保险", "金融", "理财",
        "GDP", "CPI", "PMI", "通胀", "通缩",
        "标普", "纳斯达克", "道琼斯", "恒生", "上证", "深证",
        "并购", "收购", "重组", "股份", "股权",
        "stock", "nasdaq", "dow jones", "s&p", "ipo", "fund",
        "dividend", "share", "bond", "treasury",
    ]):
        tags.add("财经")

    if source in ("bbc_zh", "voa_zh"):
        tags.add("国际")

    return list(tags)[:5]  # max 5 tags


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _build_filter_prompt(items: list[dict], rag_context: str) -> str:
    """构建 LLM 筛选 prompt — AI/Agent 优先"""
    lines = []
    for idx, it in enumerate(items):
        lines.append(
            f"[{idx}] 标题: {it['title']}\n"
            f"    来源: {it.get('source', 'unknown')}\n"
            f"    内容: {it.get('content', '')[:300]}"
        )
    joined = "\n\n".join(lines)

    rag_section = ""
    if rag_context:
        rag_section = f"\n参考历史案例（相似资讯）：\n{rag_context}\n"

    return (
        "你是一名资深新闻编辑。请对以下每条新闻按领域分别评分：\n\n"
        "AI/科技类评分标准：\n"
        "- 9-10分：划时代突破/重大模型发布/顶级开源项目\n"
        "- 7-8分：AI 行业重要动态/知名公司重大发布/重要工具\n"
        "- 5-6分：一般科技报道/边缘 AI 相关\n"
        "- 1-4分：低价值内容\n\n"
        "体育类评分标准：\n"
        "- 8-10分：顶级赛事决赛/重大转会/破纪录\n"
        "- 6-7分：热门赛事/季后赛/知名球员动态\n"
        "- 4-5分：一般赛事报道\n"
        "- 1-3分：琐碎花边\n\n"
        "时事/国际/政策类评分标准：\n"
        "- 8-10分：重大政策发布/国际重大事件\n"
        "- 6-7分：重要时事/政策解读\n"
        "- 4-5分：一般性报道\n"
        "- 1-3分：低价值内容\n\n"
        "注意：不同领域分开评判，体育/时事类不需要AI相关性也能给高分。\n\n"
        "标签从下列中选择（可多选；reason 用中文写）：\n"
        "LLM, Agent, 开源, 框架, 工具, 基础设施,\n"
        "科技, 政策, 时事, 国际, 体育\n"
        f"{rag_section}\n"
        "候选条目：\n"
        f"{joined}\n\n"
        '以JSON数组格式返回：'
        '[{"index":0,"score":8.5,"tags":["LLM","Agent"],"reason":"重要AI项目发布"}, ...]'
    )


# ---------------------------------------------------------------------------
# RAG context
# ---------------------------------------------------------------------------


async def _get_rag_context(pool, items, top_k=5) -> tuple[str, dict]:
    """RAG 检索 + 返回 (上下文文本, {url: embedding} 缓存)"""
    sample_texts = [f"{it['title']} {it.get('content', '')[:200]}" for it in items[:3]]
    sample_embs = await generate_embeddings_batch(sample_texts)

    cached_embs = {}
    if sample_embs:
        for it, emb in zip(items[:3], sample_embs):
            if emb:
                cached_embs[it.get("url", "")] = emb

    all_similar = []
    for emb in (sample_embs or []):
        if emb:
            similar = await search_similar_items(pool, emb, top_k=top_k)
            all_similar.extend(similar)

    seen_ids = set()
    context_lines = []
    for s in all_similar:
        if s["id"] not in seen_ids:
            seen_ids.add(s["id"])
            tags = ", ".join(s.get("tags", []))
            context_lines.append(
                f"- [{s['source']}] {s['title']} (相似度:{s['similarity']}, 标签:{tags})"
            )

    return "\n".join(context_lines) if context_lines else "", cached_embs


# ---------------------------------------------------------------------------
# LLM batch scoring
# ---------------------------------------------------------------------------


async def _score_items(items: list[dict], rag_context: str) -> list[dict]:
    """批量 LLM 评分，无 API Key 时回退到启发式"""
    if not _has_api_key():
        for it in items:
            it["metadata"]["ai_score"] = _mock_score_one(it)
            it["metadata"]["tags"] = _mock_tags_one(it)
            it["metadata"]["filter_reason"] = "mock"
        return items

    prompt = _build_filter_prompt(items, rag_context)
    result = await _llm_chat([
        {"role": "system",
         "content": "你是一个专业的 AI 领域新闻编辑，擅长评估 AI/Agent/LLM 新闻的重要性和价值，同时兼顾综合新闻。AI 相关内容优先给高分。始终以 JSON 格式回复，不要包含 markdown 代码块。所有 reason 和标签用中文。"},
        {"role": "user", "content": prompt},
    ], temperature=0.3, max_tokens=2000)

    if result is None:
        for it in items:
            it["metadata"]["ai_score"] = _mock_score_one(it)
            it["metadata"]["tags"] = _mock_tags_one(it)
            it["metadata"]["filter_reason"] = "llm_failed"
        return items

    try:
        scores = json.loads(_extract_json(result))
        for entry in scores:
            idx = int(entry.get("index", 0))
            if 0 <= idx < len(items):
                items[idx]["metadata"]["ai_score"] = float(entry.get("score", 5))
                items[idx]["metadata"]["tags"] = entry.get("tags", [])
                items[idx]["metadata"]["filter_reason"] = entry.get("reason", "")
    except (json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError):
        logger.warning("Score parsing failed, using mock for batch")
        for it in items:
            it["metadata"]["ai_score"] = _mock_score_one(it)
            it["metadata"]["tags"] = _mock_tags_one(it)
            it["metadata"]["filter_reason"] = "parse_failed"

    return items


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def filter_and_enrich(
    pool: asyncpg.Pool,
    items: list[dict],
    threshold: float = 6.0,
) -> tuple[list[dict], bool]:
    """LLM 筛选 + embedding 生成。

    输入：粗筛后的候选条目列表
    输出：(通过筛选的条目列表, 是否使用了LLM)
    """
    used_llm = _has_api_key()

    if used_llm:
        rag_context, cached_embs = await _get_rag_context(pool, items)
    else:
        rag_context, cached_embs = "", {}

    scored_items = await _score_items(items, rag_context)

    passed = [it for it in scored_items if it["metadata"].get("ai_score", 0) >= threshold]

    if passed:
        texts_to_embed, indices_to_embed = [], []
        for i, it in enumerate(passed):
            if it.get("url") in cached_embs:
                it["embedding"] = cached_embs[it["url"]]
            else:
                texts_to_embed.append(f"{it['title']} {it.get('content', '')[:200]}")
                indices_to_embed.append(i)
        if texts_to_embed:
            new_embs = await generate_embeddings_batch(texts_to_embed)
            if new_embs:
                for i, emb in zip(indices_to_embed, new_embs):
                    passed[i]["embedding"] = emb

    return passed, used_llm
