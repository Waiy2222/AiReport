"""去重 — URL 精确去重 + AI 语义去重 + 中文标题兜底"""
import json
import logging
import re

from .client import get_client, DEEPSEEK_MODEL
from .prompts import DEDUP_SYSTEM, dedup_user

logger = logging.getLogger(__name__)

# 中文标题相似度阈值（Jaccard，比英文更低因为中文词更少但信息密度更高）
_TITLE_JACCARD_THRESHOLD = 0.25


def url_dedup(items: list[dict]) -> list[dict]:
    """URL 精确去重：相同 URL 只保留评分最高的一条"""
    seen: dict[str, dict] = {}
    for item in items:
        url = item.get("url", "")
        if url not in seen or item.get("ai_score", 0) > seen[url].get("ai_score", 0):
            seen[url] = item
    return list(seen.values())


def _tokenize_cn(text: str) -> set[str]:
    """中文分词：提取 2+ 字词作为 token（简单但有效）"""
    # Remove punctuation and whitespace
    text = re.sub(r'[，。、；：？！\s\n\r·"\'「」『』【】《》（）\(\)\[\]{}]', '', text)
    tokens = set()
    # 2-gram: 相邻两个字符
    for i in range(len(text) - 1):
        bigram = text[i:i+2]
        # Skip if contains ASCII (keeps it for mixed content)
        tokens.add(bigram)
    # Also add 3-grams for longer matches
    for i in range(len(text) - 2):
        tokens.add(text[i:i+3])
    # Filter pure-number tokens
    return {t for t in tokens if not t.isdigit()}


def _title_dedup(items: list[dict]) -> list[dict]:
    """中文标题 Jaccard 相似度去重（API 失败时的兜底 + API 前的预处理）"""
    if len(items) <= 1:
        return items

    # Sort by score descending → keep higher-scored items
    sorted_items = sorted(items, key=lambda x: x.get("ai_score", 0), reverse=True)
    kept = []
    kept_token_sets: list[set[str]] = []

    for item in sorted_items:
        title = item.get("title", "")
        tokens = _tokenize_cn(title)

        if not tokens:
            kept.append(item)
            continue

        is_dup = False
        for existing_tokens in kept_token_sets:
            if not existing_tokens:
                continue
            overlap = len(tokens & existing_tokens)
            union = len(tokens | existing_tokens)
            if union > 0 and overlap / union > _TITLE_JACCARD_THRESHOLD:
                # Also check content overlap for confirmation
                content1 = (item.get("content") or "")[:200]
                # Find the matching kept item
                match_idx = kept_token_sets.index(existing_tokens)
                content2 = (kept[match_idx].get("content") or "")[:200]
                content_tokens1 = _tokenize_cn(content1)
                content_tokens2 = _tokenize_cn(content2)
                if content_tokens1 and content_tokens2:
                    c_overlap = len(content_tokens1 & content_tokens2)
                    c_union = len(content_tokens1 | content_tokens2)
                    if c_union > 0 and c_overlap / c_union > 0.15:
                        logger.info(
                            "Title dedup: removed '%s' (dup of '%s', title_jaccard=%.2f, content_jaccard=%.2f)",
                            title[:50], kept[match_idx].get("title", "")[:50],
                            overlap / union, c_overlap / c_union,
                        )
                        is_dup = True
                        break
                else:
                    # Only title overlap, no content to compare → still flag as dup
                    logger.info(
                        "Title dedup: removed '%s' (dup of '%s', title_jaccard=%.2f)",
                        title[:50], kept[match_idx].get("title", "")[:50], overlap / union,
                    )
                    is_dup = True
                    break

        if not is_dup:
            kept.append(item)
            kept_token_sets.append(tokens)

    removed = len(items) - len(kept)
    if removed > 0:
        logger.info("Title dedup removed %d/%d items", removed, len(items))
    return kept


async def semantic_dedup(items: list[dict]) -> list[dict]:
    """AI 语义去重：识别同一话题的条目，保留质量最高的

    增强：API 失败时回退到中文标题 Jaccard 去重（不再原样返回）。
    """
    if len(items) <= 1:
        return items

    # ① 先跑标题级去重（快速、确定、不依赖 API）
    items = _title_dedup(items)
    if len(items) <= 1:
        return items

    client = get_client()
    indexed = [{"index": i, "title": it["title"], "content": (it.get("content") or "")[:200], "source": it["source"]} for i, it in enumerate(items)]

    try:
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": DEDUP_SYSTEM},
                {"role": "user", "content": dedup_user(json.dumps(indexed, ensure_ascii=False))},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        groups = result.get("duplicate_groups", [])

        remove_indices = set()
        for g in groups:
            for idx in g.get("remove_indices", []):
                remove_indices.add(idx)

        kept = [item for i, item in enumerate(items) if i not in remove_indices]
        removed = len(items) - len(kept)
        if removed > 0:
            logger.info("Semantic dedup: removed %d items (%d remain)", removed, len(kept))
        return kept
    except Exception as e:
        logger.warning("Semantic dedup API failed (%s), title dedup already applied", str(e)[:80])
        return items  # 标题去重已在前面执行，这里安全返回
