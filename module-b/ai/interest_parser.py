"""兴趣解析 — 敏感词过滤 + 新闻相关性判断 + LLM标签提取"""
import json
import logging
from ai.client import get_client, DEEPSEEK_MODEL
from ai.sensitive_words import check_sensitive

logger = logging.getLogger(__name__)

# 与 tags.py / summarizer.py 中的标签体系保持一致
# 与 summarizer.py _ALLOWED_TAGS 保持完全一致（14 标签体系）
_ALL_TAGS: list[str] = [
    # 科技标签
    "LLM", "Agent", "开源", "工具", "科技", "行业", "全球",
    "体育", "安全", "芯片", "机器人", "自动驾驶", "融资", "医疗",
    # 用户兴趣标签
    "电子竞技", "绘画", "登山", "影视", "音乐", "咖啡", "美食", "创业",
    "环保", "汽车", "书法", "农业", "旅游", "教育", "能源", "金融",
    "大模型", "人工智能",
]

_TAG_PROMPT = """你是一个新闻兴趣解析器。用户描述了他们感兴趣的新闻类型。

**重要**：如果用户输入是多个词连在一起（如"环保音乐大模型"），必须拆分成独立标签。

可用标签：{available_tags}

用户输入：{user_input}

返回JSON：
{{"tags": ["匹配的标签1", "匹配的标签2"], "keywords": ["关键词1", "关键词2"]}}

规则：
- 用户输入可能连写多个兴趣词，需要智能拆分（如"环保音乐大模型"→["环保","音乐","大模型"]）
- 拆分后每个词从标签列表中匹配
- tags不超过5个，keywords可补充标签列表外的词
- 如果没有匹配的标签，tags 返回空数组"""

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

    # 2. 新闻相关性：不再用 LLM 判断（太激进，会误拒"书法""美食"等正常关键词）
    #    直接放行，由后续的关键词拆解 + 外部抓取能力自行判断

    return {"valid": True, "error": None}


def _simple_split(text: str) -> dict | None:
    """空格/逗号分隔 + 已知标签匹配，无需 LLM。匹配不到返回 None。"""
    import re
    words = re.split(r'[\s,，、]+', text.strip())
    words = [w for w in words if len(w) >= 1]
    if not words:
        return None
    tags = [w for w in words if w in _ALL_TAGS]
    keywords = [w for w in words if w not in _ALL_TAGS]
    if tags:
        return {"tags": tags[:5], "keywords": (tags + keywords)[:5]}
    return None


async def parse_interests(text: str) -> dict:
    """LLM 解析用户自然语言 → 标签 + 关键词。

    Returns:
        {"tags": list[str], "keywords": list[str]}
    """
    # 先尝试空格拆分直接匹配，不用 LLM（快且准确）
    simple = _simple_split(text)
    if simple and len(simple["tags"]) >= 1:
        logger.info("Simple split: tags=%s keywords=%s", simple["tags"], simple["keywords"])
        return simple

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
