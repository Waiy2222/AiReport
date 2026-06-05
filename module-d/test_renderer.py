"""TDD: module-d/renderer.py — HTML 模板渲染测试"""
import sys
import pytest

sys.path.insert(0, "module-d")
from renderer import (
    _render_header, _render_intro, _render_section,
    _render_item, _render_footer, render_article,
)


# ── _render_header ────────────────────────────────────────────────────

def test_render_header_morning():
    """早报头部"""
    result = _render_header("morning", "2026-06-05")
    assert "早报" in result
    assert "2026-06-05" in result
    assert "<h1>" in result


def test_render_header_evening():
    """晚报头部"""
    result = _render_header("evening", "2026-06-05")
    assert "晚报" in result


def test_render_header_unknown():
    """未知类型"""
    result = _render_header("unknown", "2026-06-05")
    assert "简报" in result


# ── _render_intro ─────────────────────────────────────────────────────

def test_render_intro_normal():
    """正常导语"""
    result = _render_intro(["要点1", "要点2", "要点3"])
    assert "<blockquote>" in result
    assert "<p>要点1</p>" in result
    assert "<p>要点3</p>" in result


def test_render_intro_empty():
    """空导语"""
    result = _render_intro([])
    assert result == ""


# ── _render_section ───────────────────────────────────────────────────

def test_render_section_normal():
    """正常区块"""
    section = {
        "title": "AI头条",
        "items": [
            {"title": "GPT-5", "summary": "新模型", "score": 9, "url": "http://a.com", "tags": ["LLM"]},
        ]
    }
    result = _render_section(section)
    assert "<h2>AI头条</h2>" in result
    assert "GPT-5" in result


def test_render_section_no_title():
    """无标题区块"""
    section = {"items": [{"title": "test"}]}
    result = _render_section(section)
    assert "test" in result


def test_render_section_empty():
    """空区块"""
    result = _render_section({})
    assert result == ""


# ── _render_item ──────────────────────────────────────────────────────

def test_render_item_with_url():
    """有链接的条目"""
    item = {"title": "GPT-5", "summary": "新模型", "score": 9, "url": "http://a.com", "tags": ["LLM"]}
    result = _render_item(item)
    assert 'href="http://a.com"' in result
    assert "GPT-5" in result
    assert "9/10" in result
    assert 'class="tag"' in result


def test_render_item_no_url():
    """无链接的条目"""
    item = {"title": "Test", "summary": "摘要"}
    result = _render_item(item)
    assert "<h3>Test</h3>" in result
    assert "摘要" in result


def test_render_item_no_tags():
    """无标签"""
    item = {"title": "Test"}
    result = _render_item(item)
    assert 'class="tags"' not in result


def test_render_item_empty():
    """空条目"""
    result = _render_item({})
    assert 'class="card"' in result


# ── _render_footer ────────────────────────────────────────────────────

def test_render_footer_normal():
    """正常底部"""
    result = _render_footer(["趋势1", "趋势2"])
    assert "关键趋势" in result
    assert "<li>趋势1</li>" in result
    assert "<li>趋势2</li>" in result


def test_render_footer_empty():
    """空底部"""
    result = _render_footer([])
    assert result == ""


# ── render_article ────────────────────────────────────────────────────

def test_render_article_complete():
    """完整文章渲染"""
    briefing = {
        "type": "morning",
        "date": "2026-06-05",
        "tl_dr": ["要点1"],
        "sections": [
            {"title": "AI头条", "items": [
                {"title": "GPT-5", "summary": "新模型", "score": 9, "url": "http://a.com", "tags": ["LLM"]}
            ]}
        ],
        "key_takeaways": ["趋势1"],
    }
    result = render_article(briefing)
    assert "<!DOCTYPE html>" in result
    assert "早报" in result
    assert "要点1" in result
    assert "AI头条" in result
    assert "GPT-5" in result
    assert "趋势1" in result
    assert "</html>" in result


def test_render_article_minimal():
    """最小文章"""
    briefing = {"type": "evening", "date": "2026-06-05"}
    result = render_article(briefing)
    assert "<!DOCTYPE html>" in result
    assert "晚报" in result


def test_render_article_has_css():
    """包含 CSS 样式"""
    briefing = {"type": "morning", "date": "2026-06-05"}
    result = render_article(briefing)
    assert "<style>" in result
    assert ".card" in result
