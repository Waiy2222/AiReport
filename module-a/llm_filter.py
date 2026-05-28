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
    """启发式评分：关键词+实体+来源加权"""
    combined = (item.get("title", "") + " " + item.get("content", "")).lower()
    score = 5.0

    for kw in ["发布", "开源", "release", "launch", "正式", "突破",
               "超越", "v0.", "v1.", "v2.", "v3.", "v4.", "v5."]:
        if kw.lower() in combined:
            score += 0.5

    for ent in ["deepseek", "openai", "gpt", "claude", "gemini", "llama",
                "meta", "google", "anthropic", "langchain", "agent",
                "rag", "mcp", "vllm", "chromadb", "huggingface",
                "qwen", "通义", "文心", "百川", "chatglm"]:
        if ent in combined:
            score += 0.5

    if item.get("source") in ("github", "hackernews"):
        score += 0.5

    return round(max(1.0, min(10.0, score)), 1)


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _build_filter_prompt(items: list[dict], rag_context: str) -> str:
    """构建 LLM 筛选 prompt"""
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
        "请对以下每条AI资讯进行相关性评估。\n\n"
        "评分标准：\n"
        "- 10分：重大AI突破/顶级公司重要发布/划时代开源项目\n"
        "- 8-9分：知名公司/项目动态/重要工具发布/有影响力论文\n"
        "- 6-7分：有价值的行业资讯/中等影响力开源项目\n"
        "- 4-5分：一般性技术讨论/边缘相关\n"
        "- 1-3分：与AI核心领域关联较弱\n"
        f"{rag_section}\n"
        "候选条目：\n"
        f"{joined}\n\n"
        '以JSON数组格式返回：'
        '[{"index":0,"score":8.5,"tags":["LLM","开源"],"reason":"重要开源项目发布"}, ...]'
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
            it["metadata"]["tags"] = []
            it["metadata"]["filter_reason"] = "mock"
        return items

    prompt = _build_filter_prompt(items, rag_context)
    result = await _llm_chat([
        {"role": "system",
         "content": "你是一个专业的AI资讯编辑，擅长评估资讯的重要性和相关性。始终以JSON格式回复，不要包含markdown代码块。"},
        {"role": "user", "content": prompt},
    ], temperature=0.3, max_tokens=2000)

    if result is None:
        for it in items:
            it["metadata"]["ai_score"] = _mock_score_one(it)
            it["metadata"]["tags"] = []
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
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        logger.warning("Score parsing failed, using mock for batch")
        for it in items:
            it["metadata"]["ai_score"] = _mock_score_one(it)
            it["metadata"]["tags"] = []
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
