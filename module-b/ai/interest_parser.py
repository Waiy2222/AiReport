"""兴趣解析 — 敏感词过滤 + 新闻相关性判断 + LLM标签提取"""
import json
import logging
from ai.client import get_client, DEEPSEEK_MODEL
from ai.sensitive_words import check_sensitive

logger = logging.getLogger(__name__)

# 与 tags.py / summarizer.py 中的标签体系保持一致
_ALL_TAGS: list[str] = [
    "LLM", "Agent", "开源", "AI编程", "AI产品", "AI安全", "AI政策",
    "多模态", "RAG", "基础设施", "芯片", "机器人", "自动驾驶",
    "融资", "医疗", "Python", "科技", "体育", "时事", "工具",
    "推理", "MoE", "行业", "全球",
]

_TAG_PROMPT = """你是一个新闻兴趣解析器。用户描述了他们感兴趣的新闻类型。
请从可用标签列表中选出最匹配的标签（不超过5个），并提取2-3个补充关键词。

可用标签：{available_tags}

用户输入：{user_input}

返回JSON：
{{"tags": ["匹配的标签1", "匹配的标签2"], "keywords": ["关键词1", "关键词2"]}}

规则：
- 只选择与用户描述直接相关的标签
- 如果没有匹配的标签，tags 返回空数组
- keywords 用于模糊匹配，可包含标签列表外的词"""

_NEWS_CHECK_PROMPT = """判断以下用户输入是否在描述对某类新闻/资讯的兴趣。

用户输入：{user_input}

返回JSON：{{"is_news_interest": true/false, "reason": "简短原因"}}

是新闻兴趣的例子：
- "我想看AI相关的新闻"
- "自动驾驶最新进展"
- "科技公司动态"

不是新闻兴趣的例子：
- "今天天气怎么样"
- "帮我写代码"
- "讲个笑话"
- "作业帮帮忙"
- 闲聊、问候、无关话题

规则：只要用户在表达想了解某领域的新闻/资讯/动态/进展，就算新闻兴趣。"""


async def validate_input(text: str) -> dict:
    """第一道校验：敏感词 + 新闻相关性。

    Returns:
        {"valid": bool, "error": str | None}
    """
    if not text or not text.strip():
        return {"valid": False, "error": "请输入你感兴趣的新闻领域"}

    text = text.strip()

    # 1. 敏感词检查
    hit = check_sensitive(text)
    if hit:
        logger.warning("Sensitive word detected in interest input")
        return {"valid": False, "error": "请输入有效的新闻兴趣"}

    # 2. 新闻相关性判断（轻量 LLM）
    try:
        client = get_client()
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{
                "role": "system",
                "content": _NEWS_CHECK_PROMPT.format(user_input=text[:200]),
            }],
            temperature=0,
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content.strip())

        if not result.get("is_news_interest", True):
            return {
                "valid": False,
                "error": "请输入你感兴趣的新闻领域，比如AI编程工具、自动驾驶、科技公司动态",
            }
    except Exception as e:
        logger.warning("News relevance check failed, allowing through: %s", e)
        # 校验失败不阻塞用户，直接放行

    return {"valid": True, "error": None}


async def parse_interests(text: str) -> dict:
    """LLM 解析用户自然语言 → 标签 + 关键词。

    Returns:
        {"tags": list[str], "keywords": list[str]}
    """
    try:
        client = get_client()
        resp = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{
                "role": "system",
                "content": _TAG_PROMPT.format(
                    available_tags=", ".join(_ALL_TAGS),
                    user_input=text[:300],
                ),
            }],
            temperature=0.2,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content.strip())

        # 过滤只保留已知标签
        known_tags = [t for t in result.get("tags", []) if t in _ALL_TAGS]
        keywords = result.get("keywords", [])[:3]

        return {"tags": known_tags, "keywords": keywords}
    except Exception as e:
        logger.error("Interest parsing failed: %s", e)
        return {"tags": [], "keywords": []}
