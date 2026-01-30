"""Pytest configuration and fixtures."""

import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test.db")


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
