"""Pytest configuration and fixtures."""

import pytest
import pytest_asyncio
import tempfile
import os


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test.db")


@pytest_asyncio.fixture
async def db(temp_db_path):
    """Provide a connected database instance."""
    from vibes.db import Database
    database = Database(temp_db_path)
    await database.connect()
    try:
        yield database
    finally:
        await database.close()


@pytest_asyncio.fixture
async def posts_test_client(temp_db_path):
    """Provide a test client with posts routes configured."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from unittest.mock import patch, AsyncMock
    from vibes.db import init_db, close_db
    from vibes.routes import posts

    app = web.Application()
    posts.setup_routes(app)

    await init_db(temp_db_path)
    try:
        async with TestClient(TestServer(app)) as client:
            with patch('vibes.routes.posts.queue_link_preview_fetch'):
                with patch('vibes.routes.posts.broadcast_event', new_callable=AsyncMock):
                    yield client
    finally:
        await close_db()


@pytest_asyncio.fixture
async def media_test_client(temp_db_path):
    """Provide a test client with media routes configured."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from vibes.db import init_db, close_db
    from vibes.routes import media

    app = web.Application()
    media.setup_routes(app)

    await init_db(temp_db_path)
    try:
        async with TestClient(TestServer(app)) as client:
            yield client
    finally:
        await close_db()


@pytest.fixture
def sample_post_data():
    """Sample post data for testing."""
    return {
        "type": "post",
        "content": "Hello world! #test",
        "media_ids": [],
        "link_previews": []
    }


@pytest.fixture
def sample_agent_response_data():
    """Sample agent response data for testing."""
    return {
        "type": "agent_response",
        "content": "I can help you with that.",
        "thread_id": 1,
        "agent_id": "test-agent"
    }


@pytest.fixture
def sample_media_data():
    """Sample media data for testing."""
    return {
        "filename": "test.png",
        "content_type": "image/png",
        "data": b'\x89PNG\r\n\x1a\n' + b'\x00' * 100,  # Minimal PNG-like data
        "thumbnail": b'\xff\xd8\xff' + b'\x00' * 50,  # Minimal JPEG-like data
        "metadata": {"width": 100, "height": 100}
    }


# Configure pytest-asyncio
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as an asyncio test."
    )
