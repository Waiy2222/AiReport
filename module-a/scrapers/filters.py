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
# "ai" 不应匹配 "trails"/"email", "rag" 不应匹配 "storage", "nlp" 不应匹配 "nlp"
_WORD_BOUNDARY_KW = frozenset({"ai", "rag", "nlp", "jax", "mcp", "gpt", "llm"})


def filter_ai_keywords(text: str) -> bool:
    """检查文本是否包含任一 AI 关键词（大小写不敏感）"""
    if not text:
        return False
    lower = text.lower()
    for kw in AI_KEYWORDS:
        if kw in _WORD_BOUNDARY_KW:
            if re.search(r"\b" + re.escape(kw) + r"\b", lower):
                return True
        elif kw in lower:
            return True
    return False


def filter_items_by_title(items: list[dict], field: str = "title") -> list[dict]:
    """从 dict 列表中过滤，保留 `item[field]` 包含 AI 关键词的条目"""
    return [item for item in items if filter_ai_keywords(item.get(field, ""))]
