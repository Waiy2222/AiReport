"""TDD: module-d/long_image.py — 长图 HTML 渲染 mock 测试"""
import sys
import pytest

sys.path.insert(0, "module-d")
from long_image import _render_longimage_html


# ── 测试数据 ──────────────────────────────────────────────────────────

SAMPLE = {
    "type": "morning",
    "date": "2026-06-05",
    "tl_dr": ["要点1", "要点2"],
    "sections": [
        {
            "title": "AI头条",
            "items": [
                {"title": "GPT-5", "summary": "新模型", "score": 9,
                 "url": "http://a.com", "tags": ["LLM"], "image_url": "http://img.jpg"},
            ]
        }
    ],
    "key_takeaways": ["趋势1"],
}


# ── _render_longimage_html ────────────────────────────────────────────

def test_render_html_has_header():
    """包含头部"""
    result = _render_longimage_html(SAMPLE)
    assert "早报" in result
    assert "2026-06-05" in result
    assert 'class="header"' in result


def test_render_html_evening():
    """晚报标题"""
    b = {**SAMPLE, "type": "evening"}
    result = _render_longimage_html(b)
    assert "晚报" in result


def test_render_html_has_tldr():
    """包含今日要闻"""
    result = _render_longimage_html(SAMPLE)
    assert "今日要闻" in result
    assert "要点1" in result
    assert "要点2" in result


def test_render_html_has_section():
    """包含分区"""
    result = _render_longimage_html(SAMPLE)
    assert "AI头条" in result
    assert 'class="section"' in result


def test_render_html_has_item():
    """包含条目卡片"""
    result = _render_longimage_html(SAMPLE)
    assert "GPT-5" in result
    assert "新模型" in result
    assert 'class="item-card"' in result


def test_render_html_has_image():
    """包含图片"""
    result = _render_longimage_html(SAMPLE)
    assert "http://img.jpg" in result
    assert "<img src=" in result


def test_render_html_no_image():
    """无图片时显示 fallback"""
    b = {
        "type": "morning", "date": "2026-06-05",
        "sections": [{"title": "test", "items": [{"title": "no img"}]}],
    }
    result = _render_longimage_html(b)
    assert 'class="fallback"' in result


def test_render_html_has_score():
    """包含评分"""
    result = _render_longimage_html(SAMPLE)
    assert 'class="score"' in result
    assert "9" in result


def test_render_html_has_tags():
    """包含标签"""
    result = _render_longimage_html(SAMPLE)
    assert 'class="tag"' in result
    assert "LLM" in result


def test_render_html_has_takeaways():
    """包含核心洞察"""
    result = _render_longimage_html(SAMPLE)
    assert "核心洞察" in result
    assert "趋势1" in result


def test_render_html_has_footer():
    """包含底部"""
    result = _render_longimage_html(SAMPLE)
    assert 'class="footer"' in result
    assert "自动生成" in result


def test_render_html_has_css():
    """包含 CSS 样式"""
    result = _render_longimage_html(SAMPLE)
    assert "<style>" in result
    assert "item-card" in result


def test_render_html_valid():
    """HTML 结构完整"""
    result = _render_longimage_html(SAMPLE)
    assert result.startswith("<!DOCTYPE html>")
    assert "</html>" in result


def test_render_html_empty():
    """空简报"""
    result = _render_longimage_html({})
    assert "<!DOCTYPE html>" in result
    assert "</html>" in result


def test_render_html_no_tldr():
    """无 tl_dr"""
    b = {"type": "morning", "date": "2026-06-05"}
    result = _render_longimage_html(b)
    assert "今日要闻" not in result
