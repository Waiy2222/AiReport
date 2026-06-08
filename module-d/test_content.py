"""TDD: module-d/content.py — 简报内容拆解测试"""
import sys
import pytest

sys.path.insert(0, "module-d")


# ── 测试数据 ──────────────────────────────────────────────────────────

SAMPLE_BRIEFING = {
    "type": "morning",
    "date": "2026-06-05",
    "tl_dr": ["要点1：GPT-5发布", "要点2：Agent框架更新", "要点3：开源生态活跃", "要点4：额外"],
    "sections": [
        {
            "title": "AI头条",
            "items": [
                {"title": "GPT-5发布", "summary": "OpenAI推出新模型", "score": 9, "url": "http://a.com", "tags": ["LLM"]},
                {"title": "Claude更新", "summary": "Anthropic更新", "score": 7, "url": "http://b.com", "tags": ["LLM"]},
            ]
        },
        {
            "title": "开源工具",
            "items": [
                {"title": "vLLM新版本", "summary": "推理加速", "score": 8, "url": "http://c.com", "tags": ["开源"]},
            ]
        }
    ],
    "key_takeaways": ["趋势1", "趋势2", "趋势3"],
}


# ── extract_title ─────────────────────────────────────────────────────

def test_extract_title_morning():
    """早报标题"""
    from content import extract_title
    result = extract_title(SAMPLE_BRIEFING)
    assert "早报" in result
    assert "2026-06-05" in result


def test_extract_title_evening():
    """晚报标题"""
    from content import extract_title
    b = {**SAMPLE_BRIEFING, "type": "evening"}
    result = extract_title(b)
    assert "晚报" in result


def test_extract_title_unknown():
    """未知类型"""
    from content import extract_title
    b = {**SAMPLE_BRIEFING, "type": "unknown"}
    result = extract_title(b)
    assert "简报" in result


def test_extract_title_empty():
    """空简报"""
    from content import extract_title
    result = extract_title({})
    assert "简报" in result


# ── extract_intro ─────────────────────────────────────────────────────

def test_extract_intro_normal():
    """正常取前3条"""
    from content import extract_intro
    result = extract_intro(SAMPLE_BRIEFING)
    assert len(result) == 3
    assert result[0] == "要点1：GPT-5发布"


def test_extract_intro_empty():
    """无 tl_dr"""
    from content import extract_intro
    result = extract_intro({})
    assert result == []


def test_extract_intro_few():
    """不足3条"""
    from content import extract_intro
    b = {"tl_dr": ["只有1条"]}
    result = extract_intro(b)
    assert len(result) == 1


# ── extract_body ──────────────────────────────────────────────────────

def test_extract_body_normal():
    """正常展开所有 items"""
    from content import extract_body
    result = extract_body(SAMPLE_BRIEFING)
    assert len(result) == 3  # 2 + 1


def test_extract_body_sorted():
    """按 score 降序"""
    from content import extract_body
    result = extract_body(SAMPLE_BRIEFING)
    assert result[0]["score"] == 9
    assert result[1]["score"] == 8
    assert result[2]["score"] == 7


def test_extract_body_max_items():
    """截取限制"""
    from content import extract_body
    result = extract_body(SAMPLE_BRIEFING, max_items=2)
    assert len(result) == 2


def test_extract_body_has_section_title():
    """每条 item 带 _section_title"""
    from content import extract_body
    result = extract_body(SAMPLE_BRIEFING)
    for item in result:
        assert "_section_title" in item


def test_extract_body_empty():
    """无 sections"""
    from content import extract_body
    result = extract_body({})
    assert result == []


# ── format_markdown ───────────────────────────────────────────────────

def test_format_markdown_has_title():
    """Markdown 包含标题"""
    from content import format_markdown
    result = format_markdown(SAMPLE_BRIEFING)
    assert "# AI 资讯早报" in result


def test_format_markdown_has_sections():
    """Markdown 包含章节"""
    from content import format_markdown
    result = format_markdown(SAMPLE_BRIEFING)
    assert "## AI头条" in result
    assert "## 开源工具" in result


def test_format_markdown_has_items():
    """Markdown 包含条目"""
    from content import format_markdown
    result = format_markdown(SAMPLE_BRIEFING)
    assert "GPT-5发布" in result
    assert "http://a.com" in result


def test_format_markdown_has_takeaways():
    """Markdown 包含关键趋势"""
    from content import format_markdown
    result = format_markdown(SAMPLE_BRIEFING)
    assert "关键趋势" in result
    assert "趋势1" in result


def test_format_markdown_has_tags():
    """Markdown 包含标签"""
    from content import format_markdown
    result = format_markdown(SAMPLE_BRIEFING)
    assert "`LLM`" in result


def test_format_markdown_empty():
    """空简报"""
    from content import format_markdown
    result = format_markdown({})
    assert "# " in result


# ── format_html ───────────────────────────────────────────────────────

def test_format_html_has_title():
    """HTML 包含标题"""
    from content import format_html
    result = format_html(SAMPLE_BRIEFING)
    assert "<h1>" in result
    assert "早报" in result


def test_format_html_has_sections():
    """HTML 包含章节"""
    from content import format_html
    result = format_html(SAMPLE_BRIEFING)
    assert "<h2>AI头条</h2>" in result


def test_format_html_has_links():
    """HTML 包含链接"""
    from content import format_html
    result = format_html(SAMPLE_BRIEFING)
    assert "http://a.com" in result
    assert "<a href=" in result


def test_format_html_has_tags():
    """HTML 包含标签"""
    from content import format_html
    result = format_html(SAMPLE_BRIEFING)
    assert "class='tag'" in result


def test_format_html_has_takeaways():
    """HTML 包含关键趋势"""
    from content import format_html
    result = format_html(SAMPLE_BRIEFING)
    assert "关键趋势" in result
    assert "<li>趋势1</li>" in result


def test_format_html_valid():
    """HTML 结构完整"""
    from content import format_html
    result = format_html(SAMPLE_BRIEFING)
    assert result.startswith("<!DOCTYPE html>")
    assert "</html>" in result
