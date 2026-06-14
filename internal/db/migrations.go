package db

import "log/slog"

// Schema version — bump when adding new migrations.
const schemaVersion = 2

func (db *DB) migrate() error {
	// Create schema version table
	if _, err := db.Exec(`
		CREATE TABLE IF NOT EXISTS schema_version (
			version INTEGER NOT NULL
		)
	`); err != nil {
		return err
	}

	var current int
	row := db.QueryRow("SELECT COALESCE(MAX(version), 0) FROM schema_version")
	if err := row.Scan(&current); err != nil {
		return err
	}

	if current >= schemaVersion {
		return nil
	}

	slog.Info("running migrations", "from", current, "to", schemaVersion)

	// Migration 1: initial schema
	if current < 1 {
		if err := db.migrateV1(); err != nil {
			return err
		}
	}

	// Migration 2: persisted settings/profile data
	if current < 2 {
		if err := db.migrateV2(); err != nil {
			return err
		}
	}

	// Record version
	if _, err := db.Exec("DELETE FROM schema_version"); err != nil {
		return err
	}
	_, err := db.Exec("INSERT INTO schema_version (version) VALUES (?)", schemaVersion)
	return err
}

func (db *DB) migrateV1() error {
	stmts := []string{
		// Interactions table — flexible JSON payload with virtual columns
		`CREATE TABLE IF NOT EXISTS interactions (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			timestamp DATETIME DEFAULT (datetime('now')),
			data JSON NOT NULL,
			type TEXT GENERATED ALWAYS AS (json_extract(data, '$.type')) STORED,
			thread_id INTEGER GENERATED ALWAYS AS (json_extract(data, '$.thread_id')) STORED,
			agent_id TEXT GENERATED ALWAYS AS (json_extract(data, '$.agent_id')) STORED
		)`,
		`CREATE INDEX IF NOT EXISTS idx_interactions_type ON interactions(type)`,
		`CREATE INDEX IF NOT EXISTS idx_interactions_thread ON interactions(thread_id)`,
		`CREATE INDEX IF NOT EXISTS idx_interactions_agent ON interactions(agent_id)`,
		`CREATE INDEX IF NOT EXISTS idx_interactions_ts ON interactions(timestamp DESC)`,

		// Full-text search
		`CREATE VIRTUAL TABLE IF NOT EXISTS interactions_fts USING fts5(
			content, content=interactions, content_rowid=id,
			tokenize='porter unicode61'
		)`,

		// FTS triggers
		`CREATE TRIGGER IF NOT EXISTS interactions_ai AFTER INSERT ON interactions BEGIN
			INSERT INTO interactions_fts(rowid, content)
			VALUES (new.id, json_extract(new.data, '$.content'));
		END`,
		`CREATE TRIGGER IF NOT EXISTS interactions_ad AFTER DELETE ON interactions BEGIN
			INSERT INTO interactions_fts(interactions_fts, rowid, content)
			VALUES ('delete', old.id, json_extract(old.data, '$.content'));
		END`,
		`CREATE TRIGGER IF NOT EXISTS interactions_au AFTER UPDATE ON interactions BEGIN
			INSERT INTO interactions_fts(interactions_fts, rowid, content)
			VALUES ('delete', old.id, json_extract(old.data, '$.content'));
			INSERT INTO interactions_fts(rowid, content)
			VALUES (new.id, json_extract(new.data, '$.content'));
		END`,

		// Media table — BLOBs for easy backup
		`CREATE TABLE IF NOT EXISTS media (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			filename TEXT NOT NULL,
			content_type TEXT NOT NULL,
			data BLOB NOT NULL,
			thumbnail BLOB,
			metadata JSON,
			created_at DATETIME DEFAULT (datetime('now'))
		)`,

		// Whitelist table — permission patterns
		`CREATE TABLE IF NOT EXISTS whitelist (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			pattern TEXT NOT NULL UNIQUE,
			description TEXT,
			created_at DATETIME DEFAULT (datetime('now'))
		)`,
	}

	for _, stmt := range stmts {
		if _, err := db.Exec(stmt); err != nil {
			return err
		}
	}
	return nil
}

func (db *DB) migrateV2() error {
	_, err := db.Exec(`CREATE TABLE IF NOT EXISTS settings (
		key TEXT PRIMARY KEY,
		value JSON NOT NULL,
		updated_at DATETIME DEFAULT (datetime('now'))
	)`)
	return err
}
