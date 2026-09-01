"""Shared test fixtures for module-f video pipeline tests."""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Ensure module-f is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run for ffmpeg/yt-dlp calls."""
    with patch("subprocess.run") as mock_run:
        result = MagicMock()
        result.returncode = 0
        result.stdout = "120.5"  # duration in seconds
        result.stderr = ""
        mock_run.return_value = result
        yield mock_run


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for HTTP requests (Pexels, B站 API)."""
    with patch("httpx.AsyncClient") as mock:
        client = AsyncMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {}
        response.text = ""
        mock.return_value.__aenter__.return_value = client
        mock.return_value.__aexit__.return_value = None
        yield mock


@pytest.fixture
def sample_segments():
    """Standard 4-segment news script for testing."""
    return [
        {
            "topic": "开场概述",
            "text": "各位观众早上好，欢迎收看今天的AI科技早报。今天我们将聚焦智能体领域的最新进展。",
            "broll_keywords": "AI科技 智能体 Agent",
        },
        {
            "topic": "新闻一：OpenHuman开源桌面智能体爆火",
            "text": "开源桌面AI智能体OpenHuman在GitHub上连续霸榜，六天内从三千余星飙升至近两万星，反映了开发者对本地化AI助手的强烈需求。",
            "broll_keywords": "OpenHuman 桌面智能体 GitHub",
        },
        {
            "topic": "新闻二：CrewAI多智能体框架获千万融资",
            "text": "开源多智能体协作框架CrewAI完成A轮融资，估值突破两亿美元，已被上千家企业用于自动化工作流搭建。",
            "broll_keywords": "CrewAI 多智能体 开源框架",
        },
        {
            "topic": "结尾总结",
            "text": "以上就是今天的AI智能体领域早报。从桌面智能体的爆发到多智能体协作的落地，AI智能体正在成为真正的日常工具。感谢您的收看。",
            "broll_keywords": "AI智能体 Agent",
        },
    ]


@pytest.fixture
def sample_durations():
    """TTS durations matching sample_segments (4 segments)."""
    return [8.0, 15.0, 13.0, 10.0]


@pytest.fixture(params=["asyncio"])
def anyio_backend(request):
    return request.param


@pytest.fixture(autouse=True)
def clean_env():
    """Reset environment variables before each test."""
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)
