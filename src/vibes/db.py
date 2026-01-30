"""Database layer for Vibes using SQLite with JSON columns and BLOBs."""

import aiosqlite
import json
import os
from pathlib import Path
from typing import Any, Optional
from contextlib import asynccontextmanager

DEFAULT_DB_PATH = "data/app.db"

SCHEMA_VERSION = 1

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

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
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
            await self._connection.executescript(SCHEMA)
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

    async def get_timeline(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Get timeline of interactions (newest first, root posts only)."""
        async with self._connection.execute(
            """SELECT id, timestamp, data FROM interactions 
               WHERE thread_id IS NULL 
               ORDER BY timestamp DESC 
               LIMIT ? OFFSET ?""",
            (limit, offset)
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
