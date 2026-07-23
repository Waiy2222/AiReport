"""敏感词库 — 独立文件便于维护和更新"""
import re

# 敏感词列表
SENSITIVE_WORDS: list[str] = [
    # 政治敏感类
    "六四", "天安门", "法轮功", "西藏独立", "新疆独立",
    "台独", "港独", "藏独", "疆独",
    # 色情暴力赌博类
    "色情", "赌博", "博彩", "毒品",
]


def _build_pattern(words: list[str]) -> re.Pattern:
    escaped = [re.escape(w) for w in words]
    joined = "|".join(escaped)
    return re.compile(f"({joined})", re.IGNORECASE)


_SENSITIVE_RE = _build_pattern(SENSITIVE_WORDS)


def check_sensitive(text: str) -> str | None:
    """检查文本是否包含敏感词。

    Returns:
        命中的敏感词（遮蔽后），或 None 表示通过
    """
    # 去除空格和特殊符号做规范化匹配（防绕过）
    normalized = re.sub(r'[\s\-_.,;:!?@#$%^&*()\[\]{}|\\/]', '', text)
    match = _SENSITIVE_RE.search(normalized)
    if match:
        return match.group(1)
    return None
