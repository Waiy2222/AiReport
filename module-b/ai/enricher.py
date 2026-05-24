"""背景知识补充 — 为每条资讯补充来龙去脉"""
import json
from .client import get_client, DEEPSEEK_MODEL
from .prompts import ENRICH_SYSTEM, enrich_user


async def enrich(items: list[dict], batch_size: int = 10) -> list[dict]:
    """为每条资讯补充背景知识，返回带 background 字段的 items"""
    if not items:
        return items

    client = get_client()

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        indexed = [{"index": idx, "title": it["title"], "content": (it.get("content") or "")[:200], "source": it["source"]} for idx, it in enumerate(batch)]

        try:
            resp = await client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": ENRICH_SYSTEM},
                    {"role": "user", "content": enrich_user(json.dumps(indexed, ensure_ascii=False))},
                ],
                temperature=0.5,
                response_format={"type": "json_object"},
            )
            result = json.loads(resp.choices[0].message.content)
            enrich_map = {e["index"]: e.get("background", "") for e in result.get("enriched", [])}

            for idx, item in enumerate(batch):
                item["background"] = enrich_map.get(idx, "")
        except Exception:
            for item in batch:
                item.setdefault("background", "")

    return items
