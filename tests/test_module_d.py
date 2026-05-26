"""Tests for Module D — Multi-Platform Publisher."""
import uuid
import importlib.util
import pytest
import sys, os
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

_D_DIR = os.path.join(os.path.dirname(__file__), '..', 'module-d')
sys.path.insert(0, _D_DIR)
_spec = importlib.util.spec_from_file_location("module_d_main", os.path.join(_D_DIR, "main.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["module_d_main"] = _mod
_spec.loader.exec_module(_mod)

app = _mod.app
_get_pool_or_503 = _mod._get_pool_or_503
briefing_to_title = _mod.briefing_to_title
briefing_to_markdown = _mod.briefing_to_markdown
extract_tags_from_briefing = _mod.extract_tags_from_briefing

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_pool_or_503():
    with pytest.raises(HTTPException) as exc:
        _get_pool_or_503()
    assert exc.value.status_code == 503


def test_publish_returns_503_without_db():
    response = client.post("/publish", json={"briefing_id": str(uuid.uuid4())})
    assert response.status_code == 503


def test_publish_rejects_unknown_platform():
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value={"id": "b01"})
    with patch("module_d_main._get_pool_or_503", return_value=mock_pool):
        response = client.post("/publish", json={
            "briefing_id": str(uuid.uuid4()),
            "platforms": ["unknown_platform"],
        })
        assert response.status_code == 400


def test_briefing_to_title_morning():
    assert "早报" in briefing_to_title({"type": "morning", "date": "2026-05-24"})


def test_briefing_to_title_evening():
    assert "晚报" in briefing_to_title({"type": "evening", "date": "2026-05-24"})


def test_briefing_to_markdown_structure():
    briefing = {
        "type": "morning", "date": "2026-05-24",
        "tl_dr": ["Key point 1"],
        "sections": [{"title": "AI News", "items": [{
            "title": "GPT-5 Released", "summary": "OpenAI releases GPT-5",
            "score": 9.5, "source": "github", "url": "https://example.com/1",
            "tags": ["LLM"],
        }]}],
        "key_takeaways": ["Takeaway 1"],
    }
    md = briefing_to_markdown(briefing)
    assert "# AI资讯早报" in md
    assert "## 今日要闻" in md
    assert "## AI News" in md
    assert "### GPT-5 Released" in md
    assert "## 核心要点" in md


def test_briefing_to_markdown_empty_fields():
    briefing = {"type": "evening", "date": "2026-05-24",
                "tl_dr": [], "sections": [], "key_takeaways": None}
    md = briefing_to_markdown(briefing)
    assert "AI资讯晚报" in md
    assert "核心要点" not in md


def test_extract_tags():
    briefing = {"sections": [{"items": [
        {"tags": ["AI", "LLM"]}, {"tags": ["AI", "Agent"]},
    ]}]}
    assert sorted(extract_tags_from_briefing(briefing)) == ["AI", "Agent", "LLM"]


def test_platform_modules_importable():
    from platforms import zhihu, csdn, weixin
    assert hasattr(zhihu, "publish")
    assert hasattr(csdn, "publish")
    assert hasattr(weixin, "publish")


@pytest.mark.asyncio
async def test_publish_to_returns_pending_without_credentials():
    from module_d_main import _publish_to, _credentials_configured
    for var in ["ZHIHU_CLIENT_ID", "ZHIHU_CLIENT_SECRET"]:
        os.environ.pop(var, None)
    pool = AsyncMock()
    briefing = {"id": uuid.uuid4(), "type": "morning", "date": "2026-05-24",
                "tl_dr": [], "sections": [], "key_takeaways": []}
    result = await _publish_to(pool, briefing, "zhihu")
    assert result["status"] == "pending"
