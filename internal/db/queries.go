package db

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"time"
)

// Interaction represents a row in the interactions table.
type Interaction struct {
	ID        int64           `json:"id"`
	Timestamp time.Time       `json:"timestamp"`
	Data      json.RawMessage `json:"data"`
	Type      string          `json:"type,omitempty"`
	ThreadID  *int64          `json:"thread_id,omitempty"`
	AgentID   string          `json:"agent_id,omitempty"`
}

// Media represents a row in the media table.
type Media struct {
	ID          int64           `json:"id"`
	Filename    string          `json:"filename"`
	ContentType string          `json:"content_type"`
	Data        []byte          `json:"-"`
	Thumbnail   []byte          `json:"-"`
	Metadata    json.RawMessage `json:"metadata,omitempty"`
	CreatedAt   time.Time       `json:"created_at"`
}

// MediaInfo is Media without the binary data (for listings).
type MediaInfo struct {
	ID          int64           `json:"id"`
	Filename    string          `json:"filename"`
	ContentType string          `json:"content_type"`
	Metadata    json.RawMessage `json:"metadata,omitempty"`
	CreatedAt   time.Time       `json:"created_at"`
}

// ── Interactions ─────────────────────────────────────────────────

// InsertInteraction stores a new interaction and returns its ID.
func (db *DB) InsertInteraction(data json.RawMessage) (int64, error) {
	result, err := db.Exec("INSERT INTO interactions (data) VALUES (?)", string(data))
	if err != nil {
		return 0, err
	}
	return result.LastInsertId()
}

// GetInteraction retrieves a single interaction by ID.
func (db *DB) GetInteraction(id int64) (*Interaction, error) {
	row := db.QueryRow(
		"SELECT id, timestamp, data, type, thread_id, agent_id FROM interactions WHERE id = ?", id)
	return scanInteraction(row)
}

// GetTimeline retrieves the most recent interactions, optionally before a given ID.
func (db *DB) GetTimeline(limit int, beforeID *int64) ([]Interaction, error) {
	var rows *sql.Rows
	var err error

	if beforeID != nil {
		rows, err = db.Query(
			"SELECT id, timestamp, data, type, thread_id, agent_id FROM interactions WHERE id < ? ORDER BY id DESC LIMIT ?",
			*beforeID, limit)
	} else {
		rows, err = db.Query(
			"SELECT id, timestamp, data, type, thread_id, agent_id FROM interactions ORDER BY id DESC LIMIT ?",
			limit)
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanInteractions(rows)
}

// GetThread retrieves all interactions in a thread.
func (db *DB) GetThread(threadID int64) ([]Interaction, error) {
	rows, err := db.Query(
		`SELECT id, timestamp, data, type, thread_id, agent_id FROM interactions
		 WHERE id = ? OR thread_id = ? ORDER BY id ASC`,
		threadID, threadID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanInteractions(rows)
}

// SearchInteractions performs a full-text search.
func (db *DB) SearchInteractions(query string, limit, offset int) ([]Interaction, error) {
	rows, err := db.Query(
		`SELECT i.id, i.timestamp, i.data, i.type, i.thread_id, i.agent_id
		 FROM interactions i
		 JOIN interactions_fts f ON f.rowid = i.id
		 WHERE interactions_fts MATCH ?
		 ORDER BY rank LIMIT ? OFFSET ?`,
		query, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanInteractions(rows)
}

// DeleteInteraction removes an interaction. If cascade is true, also removes replies.
func (db *DB) DeleteInteraction(id int64, cascade bool) error {
	if cascade {
		if _, err := db.Exec("DELETE FROM interactions WHERE thread_id = ?", id); err != nil {
			return err
		}
	}
	_, err := db.Exec("DELETE FROM interactions WHERE id = ?", id)
	return err
}

// ── Media ────────────────────────────────────────────────────────

// InsertMedia stores a new media file and returns its ID.
func (db *DB) InsertMedia(filename, contentType string, data, thumbnail []byte, metadata json.RawMessage) (int64, error) {
	result, err := db.Exec(
		"INSERT INTO media (filename, content_type, data, thumbnail, metadata) VALUES (?, ?, ?, ?, ?)",
		filename, contentType, data, thumbnail, string(metadata))
	if err != nil {
		return 0, err
	}
	return result.LastInsertId()
}

// GetMedia retrieves a media file with its binary data.
func (db *DB) GetMedia(id int64) (*Media, error) {
	row := db.QueryRow(
		"SELECT id, filename, content_type, data, thumbnail, metadata, created_at FROM media WHERE id = ?", id)
	m := &Media{}
	var metadata sql.NullString
	err := row.Scan(&m.ID, &m.Filename, &m.ContentType, &m.Data, &m.Thumbnail, &metadata, &m.CreatedAt)
	if err != nil {
		return nil, err
	}
	if metadata.Valid {
		m.Metadata = json.RawMessage(metadata.String)
	}
	return m, nil
}

// GetMediaInfo retrieves media metadata without the binary data.
func (db *DB) GetMediaInfo(id int64) (*MediaInfo, error) {
	row := db.QueryRow(
		"SELECT id, filename, content_type, metadata, created_at FROM media WHERE id = ?", id)
	m := &MediaInfo{}
	var metadata sql.NullString
	err := row.Scan(&m.ID, &m.Filename, &m.ContentType, &metadata, &m.CreatedAt)
	if err != nil {
		return nil, err
	}
	if metadata.Valid {
		m.Metadata = json.RawMessage(metadata.String)
	}
	return m, nil
}

// ── Whitelist ────────────────────────────────────────────────────

// AddWhitelistPattern adds a permission pattern.
func (db *DB) AddWhitelistPattern(pattern, description string) error {
	_, err := db.Exec(
		"INSERT OR IGNORE INTO whitelist (pattern, description) VALUES (?, ?)",
		pattern, description)
	return err
}

// RemoveWhitelistPattern removes a permission pattern.
func (db *DB) RemoveWhitelistPattern(pattern string) error {
	_, err := db.Exec("DELETE FROM whitelist WHERE pattern = ?", pattern)
	return err
}

// GetWhitelist returns all whitelist patterns.
func (db *DB) GetWhitelist() ([]string, error) {
	rows, err := db.Query("SELECT pattern FROM whitelist ORDER BY pattern")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var patterns []string
	for rows.Next() {
		var p string
		if err := rows.Scan(&p); err != nil {
			return nil, err
		}
		patterns = append(patterns, p)
	}
	return patterns, rows.Err()
}

// IsWhitelisted checks if a method matches any whitelist pattern.
func (db *DB) IsWhitelisted(method string) (bool, error) {
	patterns, err := db.GetWhitelist()
	if err != nil {
		return false, err
	}
	for _, p := range patterns {
		if method == p || matchGlob(p, method) {
			return true, nil
		}
	}
	return false, nil
}

// ── Helpers ──────────────────────────────────────────────────────

func scanInteraction(row *sql.Row) (*Interaction, error) {
	i := &Interaction{}
	var data string
	var threadID sql.NullInt64
	var agentID sql.NullString
	var itype sql.NullString
	err := row.Scan(&i.ID, &i.Timestamp, &data, &itype, &threadID, &agentID)
	if err != nil {
		return nil, err
	}
	i.Data = json.RawMessage(data)
	if itype.Valid {
		i.Type = itype.String
	}
	if threadID.Valid {
		i.ThreadID = &threadID.Int64
	}
	if agentID.Valid {
		i.AgentID = agentID.String
	}
	return i, nil
}

func scanInteractions(rows *sql.Rows) ([]Interaction, error) {
	var results []Interaction
	for rows.Next() {
		i := Interaction{}
		var data string
		var threadID sql.NullInt64
		var agentID sql.NullString
		var itype sql.NullString
		if err := rows.Scan(&i.ID, &i.Timestamp, &data, &itype, &threadID, &agentID); err != nil {
			return nil, err
		}
		i.Data = json.RawMessage(data)
		if itype.Valid {
			i.Type = itype.String
		}
		if threadID.Valid {
			i.ThreadID = &threadID.Int64
		}
		if agentID.Valid {
			i.AgentID = agentID.String
		}
		results = append(results, i)
	}
	return results, rows.Err()
}

// matchGlob does simple prefix/suffix glob matching (e.g., "Run *" matches "Run command").
func matchGlob(pattern, value string) bool {
	if pattern == "*" {
		return true
	}
	n := len(pattern)
	if n == 0 {
		return value == ""
	}
	if pattern[n-1] == '*' {
		return len(value) >= n-1 && value[:n-1] == pattern[:n-1]
	}
	if pattern[0] == '*' {
		suffix := pattern[1:]
		return len(value) >= len(suffix) && value[len(value)-len(suffix):] == suffix
	}
	return pattern == value
}

// InteractionData is the typed payload structure stored as JSON.
type InteractionData struct {
	Type     string `json:"type"`               // "user_message", "agent_response", "system"
	Content  string `json:"content"`            // text content
	AgentID  string `json:"agent_id,omitempty"` // which agent responded
	ThreadID *int64 `json:"thread_id,omitempty"`
	MediaIDs []int64 `json:"media_ids,omitempty"`
	// Agent-specific fields
	Model    string `json:"model,omitempty"`
	Tokens   *int   `json:"tokens,omitempty"`
}

// NewUserMessage creates an InteractionData for a user message.
func NewUserMessage(content string, mediaIDs []int64) InteractionData {
	return InteractionData{Type: "user_message", Content: content, MediaIDs: mediaIDs}
}

// NewAgentResponse creates an InteractionData for an agent response.
func NewAgentResponse(content, agentID, model string, threadID int64) InteractionData {
	return InteractionData{
		Type:     "agent_response",
		Content:  content,
		AgentID:  agentID,
		ThreadID: &threadID,
		Model:    model,
	}
}

// MarshalInteraction converts InteractionData to JSON for storage.
func MarshalInteraction(d InteractionData) (json.RawMessage, error) {
	b, err := json.Marshal(d)
	if err != nil {
		return nil, fmt.Errorf("marshal interaction: %w", err)
	}
	return b, nil
}
