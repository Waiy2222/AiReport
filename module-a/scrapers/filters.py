"""统一的关键词过滤器 — 所有 scraper 共用"""
import re

AI_KEYWORDS = [
    # 英文关键词
    "ai", "llm", "gpt", "claude", "gemini", "deepseek", "llama", "agent",
    "rag", "vector", "embedding", "transformer", "prompt",
    "fine-tuning", "rlhf", "diffusion", "stable diffusion",
    "mcp", "tool calling", "function calling",
    "langchain", "crewai", "autogpt", "vllm", "ollama", "chromadb",
    "huggingface", "pytorch", "tensorflow", "jax",
    "open source", "open-source",
    "nlp", "multimodal",
    # 中文关键词
    "大模型", "语言模型", "推理模型", "智能体",
    "开源", "多模态",
]

# 短关键词用 \b 词边界匹配，防止子串误匹配
_WORD_BOUNDARY_KW = frozenset({"ai", "rag", "nlp", "jax", "mcp", "gpt", "llm"})

# 预编译正则：短关键词一次性编译，避免每调都 re.search + re.escape
_BOUNDARY_PATTERNS = [
    re.compile(r"\b" + re.escape(kw) + r"\b", re.I)
    for kw in sorted(_WORD_BOUNDARY_KW, key=len, reverse=True)
]
# 长关键词直接 contains 匹配（不区分大小写）
_SIMPLE_KW = [
    kw for kw in AI_KEYWORDS
    if kw not in _WORD_BOUNDARY_KW
]


def filter_ai_keywords(text: str) -> bool:
    """检查文本是否包含任一 AI 关键词（大小写不敏感）"""
    if not text:
        return False
    lower = text.lower()
    for pattern in _BOUNDARY_PATTERNS:
        if pattern.search(lower):
            return True
    for kw in _SIMPLE_KW:
        if kw in lower:
            return True
    return False


def filter_items_by_title(items: list[dict], field: str = "title") -> list[dict]:
    """从 dict 列表中过滤，保留 `item[field]` 包含 AI 关键词的条目"""
    return [item for item in items if filter_ai_keywords(item.get(field, ""))]


# ── 政治敏感内容过滤 ──────────────────────────────────────────────

POLITICAL_REJECT_KEYWORDS = [
    # 领导人 / 党政机关
    "习近平", "习主席", "习大大", "总书记",
    "国务院", "中共中央", "中央军委", "中纪委", "政治局",
    "中宣部", "网信办", "统战部",
    "公安部", "国安部", "外交部发言人",
    "全国人大", "全国政协",
    # 媒体 / 宣传机器
    "央视", "新闻联播", "人民日报", "新华社",
    "环球时报", "解放军报",
    # 领土 / 主权敏感
    "台独", "藏独", "疆独", "港独",
    "六四", "天安门事件", "天安门广场",
    "法轮功", "法轮大法",
    # 军事 / 国防
    "解放军", "军队", "军区", "军委",
    "南海争端", "钓鱼岛",
    # 敏感社会议题
    "人权问题", "人权状况", "镇压", "迫害",
    "言论自由", "新闻自由", "网络审查",
    "民族冲突", "宗教迫害",
    # 国内政治 / 政策 (用户明确要求过滤)
    "国家政策", "国务院政策", "中央政策",
    "反贪", "反腐", "打黑", "维稳",
    "信访", "上访",
]

# 中文政治类通用词（不作为单独过滤词，仅辅助减弱权重）
POLITICAL_WEAK_KEYWORDS = [
    "政治", "体制", "审查", "维稳", "上访",
    "民主运动", "异议", "反党", "颠覆",
    # 政府/政党 (单独出现不拒绝，组合出现才拒绝)
    "中共", "共产党", "党员",
    "中国政府", "中国当局", "北京当局",
    "西藏", "新疆", "台湾独立", "香港独立",
    # 敏感事件
    "抗议", "示威", "游行", "集会",
    "暴力执法", "强制拆除", "强拆",
    "劳教", "劳改", "黑监狱",
    "监听", "监控", "金盾",
    "防火墙", "GFW", "Great Firewall",
    "VPN封锁", "网络封锁",
]


# 预编译：政治关键词一次性编译为单个正则
_POLITICAL_REJECT_RE = re.compile(
    "|".join(re.escape(kw) for kw in POLITICAL_REJECT_KEYWORDS),
    re.I,
)
_POLITICAL_WEAK_RE = re.compile(
    "|".join(re.escape(kw) for kw in POLITICAL_WEAK_KEYWORDS),
    re.I,
)


def reject_political_content(text: str) -> bool:
    """检查文本是否包含政治敏感内容。返回 True = 应拒绝。"""
    if not text:
        return False

    # 强关键词：命中任一即拒绝（一次正则扫描）
    if _POLITICAL_REJECT_RE.search(text):
        return True

    # 弱关键词：需要 2 个以上同时命中才拒绝
    weak_hits = len(_POLITICAL_WEAK_RE.findall(text))
    if weak_hits >= 2:
        return True

    return False


def filter_political(items: list[dict], fields: tuple = ("title", "content")) -> list[dict]:
    """过滤掉包含政治敏感内容的条目，返回干净列表。"""
    clean = []
    rejected = 0
    for item in items:
        combined = " ".join(
            str(item.get(f, "")) for f in fields if item.get(f)
        )
        if reject_political_content(combined):
            rejected += 1
        else:
            clean.append(item)
    if rejected > 0:
        import logging
        logging.getLogger(__name__).info("Political filter: rejected %d/%d items", rejected, len(items))
    return clean
