"""Database layer for Vibes using SQLite with JSON columns and BLOBs."""

import aiosqlite
import json
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

DEFAULT_DB_PATH = "data/app.db"

SCHEMA_VERSION = 3

SCHEMA = """
-- Interactions table with JSON data and virtual columns for indexing
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    data JSON NOT NULL,
    -- Virtual columns for indexing
    type TEXT GENERATED ALWAYS AS (json_extract(data, '$.type')) VIRTUAL,
    thread_id INTEGER GENERATED ALWAYS AS (json_extract(data, '$.thread_id')) VIRTUAL,
    agent_id TEXT GENERATED ALWAYS AS (json_extract(data, '$.agent_id')) VIRTUAL
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_interactions_type ON interactions(type);
CREATE INDEX IF NOT EXISTS idx_interactions_thread_id ON interactions(thread_id);
CREATE INDEX IF NOT EXISTS idx_interactions_agent_id ON interactions(agent_id);
CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp DESC);

-- Full-text search index for content (stores its own copy)
CREATE VIRTUAL TABLE IF NOT EXISTS interactions_fts USING fts5(
    content,
    tokenize='porter unicode61'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS interactions_ai AFTER INSERT ON interactions BEGIN
    INSERT INTO interactions_fts(rowid, content)
    VALUES (new.id, json_extract(new.data, '$.content'));
END;

CREATE TRIGGER IF NOT EXISTS interactions_ad AFTER DELETE ON interactions BEGIN
    DELETE FROM interactions_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS interactions_au AFTER UPDATE ON interactions BEGIN
    DELETE FROM interactions_fts WHERE rowid = old.id;
    INSERT INTO interactions_fts(rowid, content)
    VALUES (new.id, json_extract(new.data, '$.content'));
END;

-- Media table with BLOB storage for easy migration
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    data BLOB NOT NULL,
    thumbnail BLOB,
    metadata JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Permission whitelist for auto-approving agent requests
CREATE TABLE IF NOT EXISTS permission_whitelist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""

# Migration to add FTS to existing databases
MIGRATION_V3 = """
-- Add FTS5 table (stores its own copy of content)
CREATE VIRTUAL TABLE IF NOT EXISTS interactions_fts USING fts5(
    content,
    tokenize='porter unicode61'
);

-- Populate FTS from existing data
INSERT OR IGNORE INTO interactions_fts(rowid, content)
SELECT id, json_extract(data, '$.content') FROM interactions;

-- Add triggers
CREATE TRIGGER IF NOT EXISTS interactions_ai AFTER INSERT ON interactions BEGIN
    INSERT INTO interactions_fts(rowid, content)
    VALUES (new.id, json_extract(new.data, '$.content'));
END;

CREATE TRIGGER IF NOT EXISTS interactions_ad AFTER DELETE ON interactions BEGIN
    DELETE FROM interactions_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS interactions_au AFTER UPDATE ON interactions BEGIN
    DELETE FROM interactions_fts WHERE rowid = old.id;
    INSERT INTO interactions_fts(rowid, content)
    VALUES (new.id, json_extract(new.data, '$.content'));
END;
"""


class Database:
    """Async SQLite database wrapper with JSON and BLOB support."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Connect to the database and ensure schema is initialized."""
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        
        # Enable foreign keys and WAL mode for better performance
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA journal_mode = WAL")
        
        await self._init_schema()

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _init_schema(self) -> None:
        """Initialize database schema if needed."""
        # Check current schema version
        try:
            async with self._connection.execute(
                "SELECT version FROM schema_version LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
                current_version = row["version"] if row else 0
        except aiosqlite.OperationalError:
            current_version = 0

        if current_version < SCHEMA_VERSION:
            # Fresh install or base schema
            if current_version < 2:
                await self._connection.executescript(SCHEMA)
            # Migration to v3: add FTS
            if current_version < 3:
                await self._connection.executescript(MIGRATION_V3)
            
            await self._connection.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,)
            )
            await self._connection.commit()

    @asynccontextmanager
    async def transaction(self):
        """Context manager for database transactions."""
        try:
            yield self._connection
            await self._connection.commit()
        except Exception:
            await self._connection.rollback()
            raise

    # Interaction methods
    async def create_interaction(self, data: dict) -> int:
        """Create a new interaction and return its ID."""
        async with self.transaction():
            cursor = await self._connection.execute(
                "INSERT INTO interactions (data) VALUES (?)",
                (json.dumps(data),)
            )
            return cursor.lastrowid

    async def get_interaction(self, interaction_id: int) -> Optional[dict]:
        """Get an interaction by ID."""
        async with self._connection.execute(
            "SELECT id, timestamp, data FROM interactions WHERE id = ?",
            (interaction_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "data": json.loads(row["data"])
                }
            return None

    async def get_timeline(self, limit: int = 50, before_id: int = None) -> list[dict]:
        """Get timeline of all interactions (oldest first for chat view)."""
        if before_id:
            query = """SELECT id, timestamp, data
                       FROM interactions
                       WHERE id < ?
                       ORDER BY id DESC 
                       LIMIT ?"""
            params = (before_id, limit)
        else:
            query = """SELECT id, timestamp, data
                       FROM interactions
                       ORDER BY id DESC 
                       LIMIT ?"""
            params = (limit,)
        
        async with self._connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            # Reverse to get oldest-first order (chat style)
            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "data": json.loads(row["data"])
                }
                for row in reversed(rows)
            ]

    async def get_posts_by_hashtag(self, hashtag: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """Get posts containing a specific hashtag with reply counts."""
        # Search for hashtag in content (case-insensitive)
        pattern = f'%#{hashtag}%'
        async with self._connection.execute(
            """SELECT i.id, i.timestamp, i.data,
                      (SELECT COUNT(*) FROM interactions r WHERE r.thread_id = i.id) as reply_count
               FROM interactions i
               WHERE json_extract(i.data, '$.content') LIKE ? COLLATE NOCASE
               ORDER BY i.timestamp DESC 
               LIMIT ? OFFSET ?""",
            (pattern, limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "data": json.loads(row["data"]),
                    "reply_count": row["reply_count"]
                }
                for row in rows
            ]

    async def search(self, query: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """Full-text search across interaction content."""
        async with self._connection.execute(
            """SELECT i.id, i.timestamp, i.data,
                      (SELECT COUNT(*) FROM interactions r WHERE r.thread_id = i.id) as reply_count,
                      snippet(interactions_fts, 0, '<mark>', '</mark>', '...', 32) as snippet
               FROM interactions_fts fts
               JOIN interactions i ON fts.rowid = i.id
               WHERE interactions_fts MATCH ?
               ORDER BY rank
               LIMIT ? OFFSET ?""",
            (query, limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "data": json.loads(row["data"]),
                    "reply_count": row["reply_count"],
                    "snippet": row["snippet"]
                }
                for row in rows
            ]

    async def get_thread(self, thread_id: int) -> list[dict]:
        """Get all interactions in a thread."""
        async with self._connection.execute(
            """SELECT id, timestamp, data FROM interactions 
               WHERE id = ? OR thread_id = ?
               ORDER BY timestamp ASC""",
            (thread_id, thread_id)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "data": json.loads(row["data"])
                }
                for row in rows
            ]

    async def get_interactions_missing_previews(self) -> list[dict]:
        """Get interactions that have URLs in content but no link_previews."""
        async with self._connection.execute(
            """SELECT id, timestamp, data FROM interactions 
               WHERE data LIKE '%http%'
               AND (json_extract(data, '$.link_previews') IS NULL 
                    OR json_extract(data, '$.link_previews') = '[]')
               ORDER BY timestamp DESC"""
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "data": json.loads(row["data"])
                }
                for row in rows
            ]

    async def get_cached_preview(self, url: str) -> Optional[dict]:
        """Get cached OpenGraph preview by URL."""
        async with self._connection.execute(
            """SELECT id, timestamp, data FROM interactions 
               WHERE json_extract(data, '$.link_previews') IS NOT NULL
               ORDER BY timestamp DESC"""
        ) as cursor:
            async for row in cursor:
                data = json.loads(row["data"])
                for preview in data.get("link_previews", []):
                    if preview.get("url") == url:
                        return preview
        return None

    async def get_all_cached_previews(self) -> dict[str, dict]:
        """Get all cached OpenGraph previews as a URL -> preview mapping."""
        cache = {}
        async with self._connection.execute(
            """SELECT data FROM interactions 
               WHERE json_extract(data, '$.link_previews') IS NOT NULL"""
        ) as cursor:
            async for row in cursor:
                data = json.loads(row["data"])
                for preview in data.get("link_previews", []):
                    url = preview.get("url")
                    if url and url not in cache:
                        cache[url] = preview
        return cache

    async def update_interaction_previews(self, interaction_id: int, link_previews: list[dict]) -> bool:
        """Update an interaction's link_previews field."""
        async with self._connection.execute(
            "SELECT data FROM interactions WHERE id = ?",
            (interaction_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
        
        data = json.loads(row["data"])
        data["link_previews"] = link_previews
        
        async with self.transaction():
            await self._connection.execute(
                "UPDATE interactions SET data = ? WHERE id = ?",
                (json.dumps(data), interaction_id)
            )
        return True

    # Media methods
    async def create_media(
        self,
        filename: str,
        content_type: str,
        data: bytes,
        thumbnail: Optional[bytes] = None,
        metadata: Optional[dict] = None
    ) -> int:
        """Store media in the database and return its ID."""
        async with self.transaction():
            cursor = await self._connection.execute(
                """INSERT INTO media (filename, content_type, data, thumbnail, metadata) 
                   VALUES (?, ?, ?, ?, ?)""",
                (filename, content_type, data, thumbnail, 
                 json.dumps(metadata) if metadata else None)
            )
            return cursor.lastrowid

    async def get_media(self, media_id: int) -> Optional[dict]:
        """Get media by ID (without data for listing)."""
        async with self._connection.execute(
            """SELECT id, filename, content_type, metadata, created_at 
               FROM media WHERE id = ?""",
            (media_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "filename": row["filename"],
                    "content_type": row["content_type"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                    "created_at": row["created_at"]
                }
            return None

    async def get_media_by_original_url(self, original_url: str) -> Optional[int]:
        """Get media ID by original URL (for OpenGraph image caching)."""
        async with self._connection.execute(
            """SELECT id FROM media 
               WHERE json_extract(metadata, '$.original_url') = ?
               LIMIT 1""",
            (original_url,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["id"] if row else None

    async def get_media_data(self, media_id: int) -> Optional[tuple[str, bytes]]:
        """Get media content type and data blob."""
        async with self._connection.execute(
            "SELECT content_type, data FROM media WHERE id = ?",
            (media_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return (row["content_type"], row["data"])
            return None

    async def get_media_thumbnail(self, media_id: int) -> Optional[tuple[str, bytes]]:
        """Get media thumbnail (returns JPEG)."""
        async with self._connection.execute(
            "SELECT thumbnail FROM media WHERE id = ?",
            (media_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row["thumbnail"]:
                return ("image/jpeg", row["thumbnail"])
            return None

    # Permission whitelist methods
    
    async def add_to_whitelist(self, pattern: str, description: str = None) -> int:
        """Add a pattern to the permission whitelist."""
        async with self.transaction():
            cursor = await self._connection.execute(
                """INSERT OR REPLACE INTO permission_whitelist (pattern, description) 
                   VALUES (?, ?)""",
                (pattern, description)
            )
            return cursor.lastrowid
    
    async def remove_from_whitelist(self, pattern: str) -> bool:
        """Remove a pattern from the whitelist."""
        async with self.transaction():
            cursor = await self._connection.execute(
                "DELETE FROM permission_whitelist WHERE pattern = ?",
                (pattern,)
            )
            return cursor.rowcount > 0
    
    async def get_whitelist(self) -> list[dict]:
        """Get all whitelist entries."""
        async with self._connection.execute(
            "SELECT id, pattern, description, created_at FROM permission_whitelist ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "pattern": row["pattern"],
                    "description": row["description"],
                    "created_at": row["created_at"]
                }
                for row in rows
            ]
    
    async def is_whitelisted(self, title: str) -> bool:
        """Check if a tool call title matches any whitelist pattern."""
        async with self._connection.execute(
            "SELECT pattern FROM permission_whitelist"
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                pattern = row["pattern"]
                # Simple glob-style matching: * matches anything
                if pattern == "*":
                    return True
                if pattern.endswith("*"):
                    if title.startswith(pattern[:-1]):
                        return True
                elif pattern.startswith("*"):
                    if title.endswith(pattern[1:]):
                        return True
                elif pattern == title:
                    return True
            return False


# Global database instance
_db: Optional[Database] = None


async def get_db() -> Database:
    """Get the global database instance."""
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def init_db(db_path: str = DEFAULT_DB_PATH) -> Database:
    """Initialize the global database instance."""
    global _db
    _db = Database(db_path)
    await _db.connect()
    return _db


async def close_db() -> None:
    """Close the global database instance."""
    global _db
    if _db:
        await _db.close()
        _db = None
