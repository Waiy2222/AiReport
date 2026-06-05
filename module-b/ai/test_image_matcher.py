"""TDD: image_matcher.py — 配图匹配 mock 测试"""
import sys
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, "module-b")
from ai.image_matcher import (
    _get_fallback_keywords, match_image, match_images_for_briefing,
    CATEGORY_DEFAULTS,
)


# ── _get_fallback_keywords ────────────────────────────────────────────

def test_fallback_by_tag():
    """按标签匹配关键词"""
    item = {"tags": ["LLM"]}
    assert _get_fallback_keywords(item) == CATEGORY_DEFAULTS["LLM"]


def test_fallback_by_section():
    """按 section 匹配关键词"""
    item = {"tags": [], "_section_title": "大模型开源动态"}
    assert _get_fallback_keywords(item) == "large language model AI"


def test_fallback_default():
    """无匹配时返回默认"""
    item = {"tags": ["NotExist"], "_section_title": "NotExist"}
    assert _get_fallback_keywords(item) == "artificial intelligence technology"


def test_fallback_empty():
    """空 item"""
    assert _get_fallback_keywords({}) == "artificial intelligence technology"


def test_category_defaults_count():
    """分类默认值数量"""
    assert len(CATEGORY_DEFAULTS) >= 15


# ── match_image ───────────────────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_match_image_og_success():
    """Tier 1: OG 图提取成功"""
    with patch("ai.image_matcher._extract_og_image", new_callable=AsyncMock,
               return_value="https://example.com/og.jpg"):
        result = await match_image({"url": "http://a.com"})
    assert result == "https://example.com/og.jpg"


@pytest.mark.anyio(asyncio_mode="auto")
async def test_match_image_unsplash_success():
    """Tier 2: Unsplash 搜索成功"""
    with patch("ai.image_matcher._extract_og_image", new_callable=AsyncMock, return_value=None):
        with patch("ai.image_matcher._search_unsplash", new_callable=AsyncMock,
                   return_value="https://unsplash.com/img.jpg"):
            result = await match_image({"url": "http://a.com", "image_keywords": "AI robot"})
    assert result == "https://unsplash.com/img.jpg"


@pytest.mark.anyio(asyncio_mode="auto")
async def test_match_image_pexels_success():
    """Tier 2.5: Pexels 搜索成功"""
    with patch("ai.image_matcher._extract_og_image", new_callable=AsyncMock, return_value=None):
        with patch("ai.image_matcher._search_unsplash", new_callable=AsyncMock, return_value=None):
            with patch("ai.image_matcher._search_pexels", new_callable=AsyncMock,
                       return_value="https://pexels.com/img.jpg"):
                result = await match_image({"url": "http://a.com", "image_keywords": "AI"})
    assert result == "https://pexels.com/img.jpg"


@pytest.mark.anyio(asyncio_mode="auto")
async def test_match_image_fallback():
    """Tier 3/4: 全部失败时返回 Unsplash direct URL"""
    with patch("ai.image_matcher._extract_og_image", new_callable=AsyncMock, return_value=None):
        with patch("ai.image_matcher._search_unsplash", new_callable=AsyncMock, return_value=None):
            with patch("ai.image_matcher._search_pexels", new_callable=AsyncMock, return_value=None):
                result = await match_image({"tags": ["LLM"]})
    assert "unsplash.com" in result


# ── match_images_for_briefing ─────────────────────────────────────────

@pytest.mark.anyio(asyncio_mode="auto")
async def test_match_images_for_briefing():
    """为简报所有 items 匹配图片"""
    briefing = {
        "sections": [
            {"section_title": "AI头条", "items": [
                {"title": "GPT-5", "url": "http://a.com"},
            ]}
        ]
    }
    with patch("ai.image_matcher.match_image", new_callable=AsyncMock,
               return_value="https://img.jpg"):
        result = await match_images_for_briefing(briefing)
    assert result["sections"][0]["items"][0]["image_url"] == "https://img.jpg"


@pytest.mark.anyio(asyncio_mode="auto")
async def test_match_images_empty():
    """空简报"""
    result = await match_images_for_briefing({})
    assert result == {}
