"""多智能体新闻辩论 — 3 Agent 并行评分，生成多维度简报

三个角色：
  - Tech-Agent（技术派）：技术创新度、开源影响、开发者生态
  - Biz-Agent（商业派）：商业价值、市场影响、融资信号
  - Social-Agent（社会派）：社会影响、监管风险、伦理考量

策略：只对 Agent/智能体标签的新闻跑辩论，每次简报最多 3 条。
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

# 辩论覆盖除体育外的全部标签
DEBATE_TAGS = {"LLM", "Agent", "开源", "工具", "科技", "行业", "全球", "芯片", "机器人", "自动驾驶", "融资", "医疗"}
# 每次简报最多辩论条数
DEBATE_MAX_COUNT = 12
# 辩论阈值：0=不限
DEBATE_THRESHOLD = 0

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
    if valid_count < 3:
        # 凑不齐三方 → 跳过该条辩论，不写入 metadata
        logger.info(
            "Debate skipped for '%s': only %d/3 personas responded (need all 3)",
            item.get("title", "?")[:60],
            valid_count,
        )
        return None

    debate["consensus"] = "三方均给出了独立分析"
    debate["controversy"] = 3
    return debate


async def run_debate(items: list[dict], skip_tag_filter: bool = False) -> list[dict]:
    """主入口：只对 Agent/智能体 标签的新闻跑三方辩论，最多 3 条

    Args:
        items: 已评分的新闻列表（需含 ai_score + tags 字段）

    Returns:
        传入的 items，Agent 新闻的 item["metadata"]["debate"] 已填充辩论结果
    """
    # ① 筛选
    if skip_tag_filter:
        agent_items = [it for it in items if it.get("ai_score", 0) >= DEBATE_THRESHOLD]
    else:
        _FORBIDDEN = {"体育", "安全"}
        agent_items = [
            it for it in items
            if any(t in DEBATE_TAGS for t in (it.get("tags") or []))
            and not any(t in _FORBIDDEN for t in (it.get("tags") or []))
            and it.get("ai_score", 0) >= DEBATE_THRESHOLD
        ]

    # ② 按评分降序，取前 DEBATE_MAX_COUNT 条
    agent_items.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
    debate_items = agent_items[:DEBATE_MAX_COUNT]

    if not debate_items:
        logger.info(
            "Debate skipped: no AI-core items above threshold %d (tags=%s)",
            DEBATE_THRESHOLD, DEBATE_TAGS,
        )
        return items

    logger.info(
        "Starting debate for %d AI-core items (tags=%s, max=%d, threshold>=%d, total=%d)",
        len(debate_items), DEBATE_TAGS, DEBATE_MAX_COUNT, DEBATE_THRESHOLD, len(items),
    )

    # 并行对所有高分新闻跑辩论
    debate_results = await asyncio.gather(
        *[_debate_single(it) for it in debate_items],
        return_exceptions=True,
    )

    debate_count = 0
    for item, result in zip(debate_items, debate_results):
        if isinstance(result, Exception):
            logger.warning(
                "Debate failed for item '%s': %s",
                item.get("title", "?")[:50],
                result,
            )
            continue

        # 凑不齐三方 → 跳过，不写入 metadata
        if result is None:
            continue

        # 将辩论结果写入 metadata
        if isinstance(item.get("metadata"), str):
            try:
                item["metadata"] = json.loads(item["metadata"])
            except (json.JSONDecodeError, TypeError):
                item["metadata"] = {}
        if not isinstance(item.get("metadata"), dict):
            item["metadata"] = {}

        item["metadata"]["debate"] = result
        debate_count += 1

    logger.info("Debate completed for %d items (targeted %d)", debate_count, len(debate_items))
    return items
