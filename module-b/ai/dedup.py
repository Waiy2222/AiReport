"""去重 — URL 精确去重 + AI 语义去重"""
import json
from .client import get_client, DEEPSEEK_MODEL
from .prompts import DEDUP_SYSTEM, dedup_user


def url_dedup(items: list[dict]) -> list[dict]:
    """URL 精确去重：相同 URL 只保留评分最高的一条"""
    seen: dict[str, dict] = {}
    for item in items:
        url = item.get("url", "")
        if url not in seen or item.get("ai_score", 0) > seen[url].get("ai_score", 0):
            seen[url] = item
    return list(seen.values())


async def semantic_dedup(items: list[dict]) -> list[dict]:
    """AI 语义去重：识别同一话题的条目，保留质量最高的"""
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

        return [item for i, item in enumerate(items) if i not in remove_indices]
    except Exception:
        return items  # 去重失败时保留全部，不阻塞流水线
