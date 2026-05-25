"""批量评分 — 调用 DeepSeek 对资讯进行 0-10 分评分"""
import json
from .client import get_client, DEEPSEEK_MODEL
from .prompts import SCORING_SYSTEM, scoring_user


async def batch_score(items: list[dict], batch_size: int = 15) -> list[dict]:
    """批量评分，返回带 ai_score 字段的 items 列表"""
    client = get_client()
    scored_items = []

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        indexed = [{"index": idx, "title": it["title"], "content": (it.get("content") or "")[:300], "source": it["source"]} for idx, it in enumerate(batch)]

        try:
            resp = await client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": SCORING_SYSTEM},
                    {"role": "user", "content": scoring_user(json.dumps(indexed, ensure_ascii=False))},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            result = json.loads(resp.choices[0].message.content)
            score_map = {s["index"]: s for s in result.get("scores", [])}

            for idx, item in enumerate(batch):
                s = score_map.get(idx, {"score": 5.0, "reason": "评分失败"})
                item["ai_score"] = s["score"]
                item["score_reason"] = s.get("reason", "")
                scored_items.append(item)
        except Exception as e:
            # API 失败时给默认分，不阻塞流水线
            for item in batch:
                item["ai_score"] = 5.0
                item["score_reason"] = f"评分异常: {e}"
                scored_items.append(item)

    return scored_items
