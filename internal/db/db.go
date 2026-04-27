// Package db provides the SQLite database layer for Vibes.
//
// It uses modernc.org/sqlite (pure Go, no CGo) so the binary remains
// fully self-contained. The schema uses JSON columns with virtual columns
// for indexing, matching the Python vibes implementation.
package db

import (
	"database/sql"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sync"

	_ "modernc.org/sqlite"
)

// DB wraps a sql.DB connection with Vibes-specific helpers.
type DB struct {
	*sql.DB
	mu   sync.RWMutex
	path string
}

// Open creates or opens a SQLite database at the given path.
// It runs migrations automatically.
func Open(path string) (*DB, error) {
	// Ensure directory exists
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("create db dir: %w", err)
	}

	dsn := fmt.Sprintf("file:%s?_journal_mode=WAL&_busy_timeout=5000&_synchronous=NORMAL&_foreign_keys=ON", path)
	sqlDB, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}

	// Single writer, multiple readers
	sqlDB.SetMaxOpenConns(1)

	db := &DB{DB: sqlDB, path: path}

	if err := db.migrate(); err != nil {
		sqlDB.Close()
		return nil, fmt.Errorf("migrate: %w", err)
	}

	slog.Info("database opened", "path", path)
	return db, nil
}

// Path returns the database file path.
func (db *DB) Path() string { return db.path }
