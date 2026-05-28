"""Shared test fixtures for all modules."""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakeConnCtx:
    """Async context manager that returns a mock connection.

    asyncpg.Pool.acquire() returns an async context manager, NOT a coroutine.
    Using ``async with pool.acquire() as conn:`` calls __aenter__ on the
    return value, not on the result of awaiting it.
    """
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def mock_pool():
    """Mock asyncpg Pool supporting ``async with pool.acquire() as conn:``."""
    pool = AsyncMock()
    conn = AsyncMock()

    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=0)
    conn.execute = AsyncMock(return_value="OK")

    # conn.transaction() also returns an async context manager
    conn.transaction = MagicMock(return_value=_FakeConnCtx(conn))

    # pool.acquire() returns an async context manager (not a coroutine)
    pool.acquire = MagicMock(return_value=_FakeConnCtx(conn))

    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchval = AsyncMock(return_value=0)
    pool.execute = AsyncMock(return_value="OK")

    return pool


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for HTTP requests."""
    with patch("httpx.AsyncClient") as mock:
        client = AsyncMock()
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.return_value = {}
        client.post.return_value = response
        client.get.return_value = response
        mock.return_value.__aenter__.return_value = client
        mock.return_value.__aexit__.return_value = None
        yield mock


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
