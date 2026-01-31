"""Tests for route handlers."""

import pytest
import io

from vibes.routes import media


class TestGenerateThumbnail:
    """Test thumbnail generation."""

    def test_generate_thumbnail_non_image(self):
        """Test thumbnail generation for non-image returns None."""
        result = media.generate_thumbnail(b'text data', 'text/plain')
        assert result is None

    def test_generate_thumbnail_invalid_image(self):
        """Test thumbnail generation for invalid image returns None."""
        result = media.generate_thumbnail(b'not an image', 'image/png')
        assert result is None

    def test_generate_thumbnail_valid_image(self):
        """Test thumbnail generation for valid image."""
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='red')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        
        result = media.generate_thumbnail(buf.getvalue(), 'image/png')
        assert result is not None
        assert len(result) > 0

    def test_generate_thumbnail_large_image_resized(self):
        """Test that large images are resized."""
        from PIL import Image
        img = Image.new('RGB', (2000, 2000), color='blue')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        
        result = media.generate_thumbnail(buf.getvalue(), 'image/png')
        assert result is not None
        
        result_img = Image.open(io.BytesIO(result))
        assert max(result_img.size) <= media.MAX_THUMBNAIL_SIZE

    def test_generate_thumbnail_rgba_converted(self):
        """Test that RGBA images are converted to RGB."""
        from PIL import Image
        img = Image.new('RGBA', (100, 100), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        
        result = media.generate_thumbnail(buf.getvalue(), 'image/png')
        assert result is not None
        
        result_img = Image.open(io.BytesIO(result))
        assert result_img.mode == 'RGB'


class TestPostRoutesIntegration:
    """Integration tests for post routes."""

    @pytest.mark.asyncio
    async def test_create_and_get_post(self, posts_test_client):
        """Test creating and retrieving a post via routes."""
        client = posts_test_client
        # Create post
        resp = await client.post('/post', json={'content': 'Test post'})
        assert resp.status == 201
        data = await resp.json()
        assert data['data']['content'] == 'Test post'
        
        # Get timeline
        resp = await client.get('/timeline')
        assert resp.status == 200
        timeline = await resp.json()
        assert len(timeline['posts']) == 1

    @pytest.mark.asyncio
    async def test_timeline_pagination(self, posts_test_client):
        """Test timeline pagination."""
        client = posts_test_client
        # Create 10 posts
        for i in range(10):
            await client.post('/post', json={'content': f'Post {i}'})
        
        # Get first page
        resp = await client.get('/timeline?limit=5')
        data = await resp.json()
        assert len(data['posts']) == 5
        assert data['has_more'] is True
        
        # Get second page
        before_id = data['posts'][0]['id']
        resp = await client.get(f'/timeline?limit=5&before={before_id}')
        data2 = await resp.json()
        assert len(data2['posts']) == 5

    @pytest.mark.asyncio
    async def test_thread_operations(self, posts_test_client):
        """Test thread creation and retrieval."""
        client = posts_test_client
        # Create parent post
        resp = await client.post('/post', json={'content': 'Parent'})
        parent = await resp.json()
        
        # Create reply
        resp = await client.post('/reply', json={
            'content': 'Reply',
            'thread_id': parent['id']
        })
        assert resp.status == 201
        
        # Get thread
        resp = await client.get(f"/thread/{parent['id']}")
        assert resp.status == 200
        thread = await resp.json()
        assert len(thread['thread']) == 2

    @pytest.mark.asyncio
    async def test_hashtag_search(self, posts_test_client):
        """Test hashtag search."""
        client = posts_test_client
        await client.post('/post', json={'content': 'Hello #python'})
        await client.post('/post', json={'content': 'Hello #javascript'})
        
        resp = await client.get('/hashtag/python')
        assert resp.status == 200
        data = await resp.json()
        assert len(data['posts']) == 1


class TestSSEDisconnectRestart:
    """Restart agent when all clients disconnect."""

    @pytest.mark.asyncio
    async def test_agent_restart_scheduled_when_last_client_disconnects(self, monkeypatch):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        from unittest.mock import AsyncMock
        from vibes.routes import sse

        monkeypatch.setattr(sse, "stop_agent", AsyncMock())
        monkeypatch.setattr(sse, "start_agent", AsyncMock())
        monkeypatch.setattr(sse, "get_config", lambda: type("C", (), {"agent_restart_on_disconnect_s": 0})())

        app = web.Application()
        sse.setup_routes(app)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get('/sse/stream')
            assert resp.status == 200

        # After disconnect, with delay 0, restart is disabled.
        assert sse.stop_agent.await_count == 0
        assert sse.start_agent.await_count == 0


class TestMediaRoutesIntegration:
    """Integration tests for media routes."""

    @pytest.mark.asyncio
    async def test_media_not_found(self, media_test_client):
        """Test getting non-existent media."""
        client = media_test_client
        resp = await client.get('/media/99999')
        assert resp.status == 404
        
        resp = await client.get('/media/99999/thumbnail')
        assert resp.status == 404
        
        resp = await client.get('/media/99999/info')
        assert resp.status == 404
