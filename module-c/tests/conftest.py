"""Module C tests — conftest"""
import os
import sys
import pytest
import asyncpg

# 确保 backend 目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from httpx import ASGITransport, AsyncClient
from main import app
from db import init_db, close_db, get_pool

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ai_news",
)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def test_db():
    """初始化测试数据库连接"""
    try:
        await init_db()
    except Exception:
        # Pool already initialized
        pass
    yield
    # 不关闭连接池，后续测试复用


@pytest.fixture
async def client():
    """FastAPI TestClient"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
