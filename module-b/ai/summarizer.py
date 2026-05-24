"""摘要 + 标签生成 — 生成结构化简报内容"""
import json
from .client import get_client, DEEPSEEK_MODEL
from .prompts import get_summary_system, summary_user


async def summarize(items: list[dict], briefing_type: str) -> dict:
    """生成简报的 tl_dr / sections / key_takeaways"""
    if not items:
        return {"tl_dr": [], "sections": [], "key_takeaways": []}

    client = get_client()
    indexed = []
    for i, it in enumerate(items):
        indexed.append({
            "index": i,
            "title": it["title"],
            "content": (it.get("content") or "")[:300],
            "source": it["source"],
            "url": it.get("url", ""),
            "score": it.get("ai_score", 0),
            "background": it.get("background", ""),
        })

    system_prompt = get_summary_system(briefing_type)

    try:
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": summary_user(json.dumps(indexed, ensure_ascii=False), briefing_type)},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        return {
            "tl_dr": result.get("tl_dr", []),
            "sections": result.get("sections", []),
            "key_takeaways": result.get("key_takeaways", []),
        }
    except Exception as e:
        return {
            "tl_dr": [f"处理异常: {e}"],
            "sections": [],
            "key_takeaways": [],
        }
