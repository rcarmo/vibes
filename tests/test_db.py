"""Tests for the database layer."""

import pytest
import json
from vibes.db import Database, init_db, close_db, get_db


class TestDatabase:
    """Test Database class."""

    @pytest.mark.asyncio
    async def test_connect_creates_tables(self, temp_db_path):
        """Test that connecting creates the schema."""
        db = Database(temp_db_path)
        await db.connect()
        
        # Check that tables exist
        async with db._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cursor:
            tables = [row[0] for row in await cursor.fetchall()]
        
        assert "interactions" in tables
        assert "media" in tables
        assert "schema_version" in tables
        
        await db.close()

    @pytest.mark.asyncio
    async def test_create_and_get_interaction(self, temp_db_path, sample_post_data):
        """Test creating and retrieving an interaction."""
        db = Database(temp_db_path)
        await db.connect()
        
        # Create interaction
        interaction_id = await db.create_interaction(sample_post_data)
        assert interaction_id > 0
        
        # Get interaction
        result = await db.get_interaction(interaction_id)
        assert result is not None
        assert result["id"] == interaction_id
        assert result["data"]["content"] == sample_post_data["content"]
        assert result["data"]["type"] == "post"
        
        await db.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent_interaction(self, temp_db_path):
        """Test getting a non-existent interaction returns None."""
        db = Database(temp_db_path)
        await db.connect()
        
        result = await db.get_interaction(99999)
        assert result is None
        
        await db.close()

    @pytest.mark.asyncio
    async def test_get_timeline(self, temp_db_path, sample_post_data):
        """Test getting timeline of interactions."""
        db = Database(temp_db_path)
        await db.connect()
        
        # Create multiple interactions
        ids = []
        for i in range(5):
            data = {**sample_post_data, "content": f"Post {i}"}
            ids.append(await db.create_interaction(data))
        
        # Get timeline (should be oldest first)
        timeline = await db.get_timeline(limit=10)
        assert len(timeline) == 5
        assert timeline[0]["data"]["content"] == "Post 0"
        assert timeline[4]["data"]["content"] == "Post 4"
        
        await db.close()

    @pytest.mark.asyncio
    async def test_get_timeline_with_before_id(self, temp_db_path, sample_post_data):
        """Test timeline pagination with before_id cursor."""
        db = Database(temp_db_path)
        await db.connect()
        
        # Create 10 interactions
        ids = []
        for i in range(10):
            data = {**sample_post_data, "content": f"Post {i}"}
            ids.append(await db.create_interaction(data))
        
        # Get first page (most recent 5)
        page1 = await db.get_timeline(limit=5)
        assert len(page1) == 5
        
        # Get second page using before_id
        oldest_from_page1 = page1[0]["id"]
        page2 = await db.get_timeline(limit=5, before_id=oldest_from_page1)
        assert len(page2) == 5
        
        # Verify no overlap
        page1_ids = {p["id"] for p in page1}
        page2_ids = {p["id"] for p in page2}
        assert page1_ids.isdisjoint(page2_ids)
        
        await db.close()

    @pytest.mark.asyncio
    async def test_get_posts_by_hashtag(self, temp_db_path):
        """Test searching posts by hashtag."""
        db = Database(temp_db_path)
        await db.connect()
        
        # Create posts with different hashtags
        await db.create_interaction({"type": "post", "content": "Hello #python"})
        await db.create_interaction({"type": "post", "content": "Hello #javascript"})
        await db.create_interaction({"type": "post", "content": "More #python stuff"})
        
        # Search for python hashtag
        results = await db.get_posts_by_hashtag("python")
        assert len(results) == 2
        
        # Search for javascript hashtag
        results = await db.get_posts_by_hashtag("javascript")
        assert len(results) == 1
        
        # Search for non-existent hashtag
        results = await db.get_posts_by_hashtag("rust")
        assert len(results) == 0
        
        await db.close()

    @pytest.mark.asyncio
    async def test_get_thread(self, temp_db_path, sample_post_data, sample_agent_response_data):
        """Test getting a thread with replies."""
        db = Database(temp_db_path)
        await db.connect()
        
        # Create parent post
        parent_id = await db.create_interaction(sample_post_data)
        
        # Create reply
        reply_data = {**sample_agent_response_data, "thread_id": parent_id}
        await db.create_interaction(reply_data)
        
        # Get thread
        thread = await db.get_thread(parent_id)
        assert len(thread) == 2
        assert thread[0]["id"] == parent_id
        assert thread[1]["data"]["thread_id"] == parent_id
        
        await db.close()

    @pytest.mark.asyncio
    async def test_update_interaction_previews(self, temp_db_path, sample_post_data):
        """Test updating link previews on an interaction."""
        db = Database(temp_db_path)
        await db.connect()
        
        # Create interaction with URL
        data = {**sample_post_data, "content": "Check out https://example.com"}
        interaction_id = await db.create_interaction(data)
        
        # Update with preview
        previews = [{"url": "https://example.com", "title": "Example"}]
        success = await db.update_interaction_previews(interaction_id, previews)
        assert success is True
        
        # Verify update
        result = await db.get_interaction(interaction_id)
        assert result["data"]["link_previews"] == previews
        
        await db.close()

    @pytest.mark.asyncio
    async def test_update_nonexistent_interaction_previews(self, temp_db_path):
        """Test updating previews on non-existent interaction."""
        db = Database(temp_db_path)
        await db.connect()
        
        success = await db.update_interaction_previews(99999, [])
        assert success is False
        
        await db.close()


class TestMedia:
    """Test media storage methods."""

    @pytest.mark.asyncio
    async def test_create_and_get_media(self, temp_db_path, sample_media_data):
        """Test creating and retrieving media."""
        db = Database(temp_db_path)
        await db.connect()
        
        # Create media
        media_id = await db.create_media(
            filename=sample_media_data["filename"],
            content_type=sample_media_data["content_type"],
            data=sample_media_data["data"],
            thumbnail=sample_media_data["thumbnail"],
            metadata=sample_media_data["metadata"]
        )
        assert media_id > 0
        
        # Get media metadata
        result = await db.get_media(media_id)
        assert result is not None
        assert result["filename"] == "test.png"
        assert result["content_type"] == "image/png"
        assert result["metadata"]["width"] == 100
        
        await db.close()

    @pytest.mark.asyncio
    async def test_get_media_data(self, temp_db_path, sample_media_data):
        """Test retrieving media blob data."""
        db = Database(temp_db_path)
        await db.connect()
        
        media_id = await db.create_media(
            filename=sample_media_data["filename"],
            content_type=sample_media_data["content_type"],
            data=sample_media_data["data"]
        )
        
        result = await db.get_media_data(media_id)
        assert result is not None
        content_type, data = result
        assert content_type == "image/png"
        assert data == sample_media_data["data"]
        
        await db.close()

    @pytest.mark.asyncio
    async def test_get_media_thumbnail(self, temp_db_path, sample_media_data):
        """Test retrieving media thumbnail."""
        db = Database(temp_db_path)
        await db.connect()
        
        media_id = await db.create_media(
            filename=sample_media_data["filename"],
            content_type=sample_media_data["content_type"],
            data=sample_media_data["data"],
            thumbnail=sample_media_data["thumbnail"]
        )
        
        result = await db.get_media_thumbnail(media_id)
        assert result is not None
        content_type, data = result
        assert content_type == "image/jpeg"
        assert data == sample_media_data["thumbnail"]
        
        await db.close()

    @pytest.mark.asyncio
    async def test_get_media_by_original_url(self, temp_db_path, sample_media_data):
        """Test finding media by original URL."""
        db = Database(temp_db_path)
        await db.connect()
        
        # Create media with original_url in metadata
        metadata = {"original_url": "https://example.com/image.png"}
        media_id = await db.create_media(
            filename="cached.png",
            content_type="image/png",
            data=sample_media_data["data"],
            metadata=metadata
        )
        
        # Find by URL
        found_id = await db.get_media_by_original_url("https://example.com/image.png")
        assert found_id == media_id
        
        # Not found
        not_found = await db.get_media_by_original_url("https://other.com/image.png")
        assert not_found is None
        
        await db.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent_media(self, temp_db_path):
        """Test getting non-existent media."""
        db = Database(temp_db_path)
        await db.connect()
        
        assert await db.get_media(99999) is None
        assert await db.get_media_data(99999) is None
        assert await db.get_media_thumbnail(99999) is None
        
        await db.close()


class TestGlobalDatabase:
    """Test global database functions."""

    @pytest.mark.asyncio
    async def test_init_and_close_db(self, temp_db_path):
        """Test initializing and closing global database."""
        db = await init_db(temp_db_path)
        assert db is not None
        
        # Should be able to get the same instance
        same_db = await get_db()
        assert same_db is db
        
        await close_db()
        
        # Should raise after close
        with pytest.raises(RuntimeError):
            await get_db()

    @pytest.mark.asyncio
    async def test_get_db_without_init_raises(self):
        """Test that get_db raises when not initialized."""
        # Ensure db is closed
        await close_db()
        
        with pytest.raises(RuntimeError, match="Database not initialized"):
            await get_db()
