"""批量评分 — 调用 DeepSeek 对资讯进行 0-10 分评分 + 标签清洗"""
import json
import logging
import re
from .client import get_client, DEEPSEEK_MODEL
from .prompts import SCORING_SYSTEM, scoring_user

logger = logging.getLogger(__name__)

# 允许的标签白名单（LLM 返回的不合法标签会被过滤替换）
_ALLOWED_TAGS = {
    "LLM", "Agent", "开源", "工具", "科技", "行业", "全球",
    "体育", "安全", "芯片", "机器人", "自动驾驶", "融资", "医疗",
}

# 关键词→标签映射（兜底：当 LLM 返回的标签全部不合法时使用）
_KEYWORD_TAG_MAP = [
    (re.compile(r"LLM|大模型|GPT|Claude|Gemini|transformer|语言模型", re.I), "LLM"),
    (re.compile(r"agent|智能体|代理|AI代理", re.I), "Agent"),
    (re.compile(r"开源|open.source|github|repo\b|gitlab|Apache", re.I), "开源"),
    (re.compile(r"tool|插件|plugin|sdk|cli\b|api\b|框架|开发者工具|IDE", re.I), "工具"),
    (re.compile(r"芯片|chip|nvidia|intel|amd|半导体|gpu|cpu|处理器|显卡", re.I), "芯片"),
    (re.compile(r"机器人|robot|automation|人形|机械臂|具身智能", re.I), "机器人"),
    (re.compile(r"自动驾驶|self.driv|autonomous|无人驾驶|无人车", re.I), "自动驾驶"),
    (re.compile(r"融资|IPO|上市|投资|估值|b轮|a轮|参投|创投|亿元|万美元", re.I), "融资"),
    (re.compile(r"体育|sport|nba|nfl|nhl|足球|篮球|比赛|赛事|冠军|WNBA|UFC", re.I), "体育"),
    (re.compile(r"安全|security|漏洞|攻击|黑客|隐私|泄露|虚假广告|起诉", re.I), "安全"),
    (re.compile(r"医疗|医学|health|药物|临床|制药", re.I), "医疗"),
    (re.compile(r"国际|外交|贸易|制裁|关税|白宫|美国|欧洲", re.I), "全球"),
    (re.compile(r"政策|监管|法规|政府|法院|法案|条例|合规|审查", re.I), "行业"),
    (re.compile(r"AI|人工智能|科技|tech\b|大疆|百度|阿里|腾讯|字节|OpenAI|Anthropic", re.I), "科技"),
]


def _clean_tags(raw_tags: list[str], title: str = "", content: str = "") -> list[str]:
    """清洗 LLM 返回的标签：保留白名单中的，替换不合法的"""
    clean = [t for t in raw_tags if t in _ALLOWED_TAGS]
    if clean:
        return clean[:2]

    # 兜底：根据标题/内容关键词匹配
    text = f"{title} {content or ''}"[:200]
    for pattern, tag in _KEYWORD_TAG_MAP:
        if pattern.search(text):
            clean.append(tag)
        if len(clean) >= 2:
            break

    if not clean:
        clean = ["科技"]
    return clean[:2]


async def batch_score(items: list[dict], batch_size: int = 15) -> list[dict]:
    """批量评分，返回带 ai_score + cleaned tags 的 items 列表"""
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
                s = score_map.get(idx, {"score": 5.0, "reason": "评分失败", "tags": []})
                raw_tags = s.get("tags", [])
                item["ai_score"] = s["score"]
                item["score_reason"] = s.get("reason", "")
                item["tags"] = _clean_tags(raw_tags, item.get("title", ""), item.get("content", ""))
                scored_items.append(item)
        except Exception as e:
            logger.error("Batch score API call failed: %s", str(e)[:80])
            for item in batch:
                item["ai_score"] = 5.0
                item["score_reason"] = f"评分异常"
                item["tags"] = _clean_tags([], item.get("title", ""), item.get("content", ""))
                scored_items.append(item)

    # 统计标签分布
    from collections import Counter
    all_tags = [t for it in scored_items for t in it.get("tags", [])]
    logger.info("Tag distribution: %s", dict(Counter(all_tags).most_common(10)))
    return scored_items
