"""多智能体新闻辩论 — 3 Agent 并行评分，生成多维度简报

三个角色：
  - Tech-Agent（技术派）：技术创新度、开源影响、开发者生态
  - Biz-Agent（商业派）：商业价值、市场影响、融资信号
  - Social-Agent（社会派）：社会影响、监管风险、伦理考量

策略：只对 ai_score >= 8 的 Top 新闻跑辩论，控制成本。
辩论失败时静默回退，不阻塞主流水线。
"""
import asyncio
import json
import logging

from .client import get_client, DEEPSEEK_MODEL
from .prompts import (
    DEBATE_TECH_PROMPT,
    DEBATE_BIZ_PROMPT,
    DEBATE_SOCIAL_PROMPT,
    debate_user,
)

logger = logging.getLogger(__name__)

# 辩论阈值：只对 8 分以上新闻跑辩论
DEBATE_THRESHOLD = 8

# 角色配置: (角色名, system_prompt, 视角缩写)
PERSONAS = [
    ("Tech-Agent", DEBATE_TECH_PROMPT, "tech_view"),
    ("Biz-Agent", DEBATE_BIZ_PROMPT, "biz_view"),
    ("Social-Agent", DEBATE_SOCIAL_PROMPT, "social_view"),
]


def _build_item_json(item: dict) -> str:
    """构建单条新闻的简要 JSON，供 Agent 分析（限制长度控制 token）"""
    return json.dumps(
        {
            "title": item.get("title", ""),
            "content": (item.get("content") or "")[:300],
            "source": item.get("source", ""),
            "ai_score": item.get("ai_score", 0),
            "tags": item.get("tags", []),
        },
        ensure_ascii=False,
    )


async def _query_persona(persona_name: str, system_prompt: str, item: dict) -> str | None:
    """让单个 Agent 角色给出一条新闻的观点"""
    client = get_client()
    item_json = _build_item_json(item)
    try:
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": debate_user(item_json)},
            ],
            temperature=0.7,
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(
            "Debate agent %s failed for item '%s': %s",
            persona_name,
            item.get("title", "?")[:50],
            e,
        )
        return None


async def _debate_single(item: dict) -> dict:
    """对单条新闻跑 3 个 Agent 并行辩论"""
    tasks = []
    for name, prompt, key in PERSONAS:
        tasks.append(_query_persona(name, prompt, item))

    results = await asyncio.gather(*tasks)

    debate = {}
    for (name, prompt, key), result in zip(PERSONAS, results):
        debate[key] = result or f"[{name} 分析暂不可用]"

    # 计算共识/争议度（基于三方可否给出有效观点）
    valid_count = sum(1 for v in debate.values() if v and "暂不可用" not in v)
    if valid_count == 3:
        consensus = "三方均给出了独立分析"
        controversy = 3
    elif valid_count == 2:
        consensus = "两方给出有效分析"
        controversy = 5
    elif valid_count == 1:
        consensus = "仅一方给出分析"
        controversy = 7
    else:
        consensus = "三方分析暂不可用"
        controversy = 0

    debate["consensus"] = consensus
    debate["controversy"] = controversy

    return debate


async def run_debate(items: list[dict]) -> list[dict]:
    """主入口：对每条高优先级新闻跑 3 个 Agent 辩论

    Args:
        items: 已评分的新闻列表（需含 ai_score 字段）

    Returns:
        传入的 items，高分的 item["metadata"]["debate"] 已填充辩论结果
    """
    # 只对 ai_score >= 8 的 Top 新闻跑辩论
    debate_items = [it for it in items if it.get("ai_score", 0) >= DEBATE_THRESHOLD]

    if not debate_items:
        logger.info("No items reach debate threshold (score >= %d)", DEBATE_THRESHOLD)
        return items

    logger.info(
        "Starting debate for %d/%d items (threshold >= %d)",
        len(debate_items),
        len(items),
        DEBATE_THRESHOLD,
    )

    # 并行对所有高分新闻跑辩论
    debate_results = await asyncio.gather(
        *[_debate_single(it) for it in debate_items],
        return_exceptions=True,
    )

    for item, result in zip(debate_items, debate_results):
        if isinstance(result, Exception):
            logger.warning(
                "Debate failed for item '%s': %s",
                item.get("title", "?")[:50],
                result,
            )
            result = {
                "tech_view": "分析暂不可用",
                "biz_view": "分析暂不可用",
                "social_view": "分析暂不可用",
                "consensus": "辩论异常",
                "controversy": 0,
            }

        # 将辩论结果写入 metadata
        if isinstance(item.get("metadata"), str):
            try:
                item["metadata"] = json.loads(item["metadata"])
            except (json.JSONDecodeError, TypeError):
                item["metadata"] = {}
        if not isinstance(item.get("metadata"), dict):
            item["metadata"] = {}

        item["metadata"]["debate"] = result

    logger.info("Debate completed for %d items", len(debate_items))
    return items
