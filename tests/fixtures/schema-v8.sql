-- Schema provenance: vibes 51aac18, db.py SCHEMA plus migrations v3-v8.

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

-- Active agent turns for crash recovery
CREATE TABLE IF NOT EXISTS active_turns (
    turn_id TEXT PRIMARY KEY,
    thread_id INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_status JSON
);


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


-- Active agent turns for crash recovery
CREATE TABLE IF NOT EXISTS active_turns (
    turn_id TEXT PRIMARY KEY,
    thread_id INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_status JSON
);


CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT REFERENCES chat_sessions(id) ON DELETE SET NULL,
    archived INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO chat_sessions (id, name) VALUES ('default', 'Default');


CREATE TABLE IF NOT EXISTS chat_session_backends (
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    backend TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    model TEXT,
    thinking_level TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, backend)
);


CREATE TABLE IF NOT EXISTS model_preferences (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    pins TEXT NOT NULL DEFAULT '[]'
);
INSERT OR IGNORE INTO model_preferences(singleton, pins) VALUES (1, '[]');


CREATE TABLE IF NOT EXISTS session_plans (
    session_id TEXT PRIMARY KEY REFERENCES chat_sessions(id) ON DELETE CASCADE,
    markdown TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL CHECK (revision >= 1),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

DELETE FROM schema_version;
INSERT INTO schema_version(version) VALUES(8);
