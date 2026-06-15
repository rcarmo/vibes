package db

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
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

// LocalServiceAudit stores sanitized ACP/local-service audit metadata. It must
// not contain full file contents, terminal output, secrets, or raw environment.
type LocalServiceAudit struct {
	ID         int64           `json:"id"`
	Timestamp  time.Time       `json:"timestamp"`
	Type       string          `json:"type"`
	ProviderID string          `json:"provider_id,omitempty"`
	SessionID  string          `json:"session_id,omitempty"`
	Method     string          `json:"method"`
	RequestID  string          `json:"request_id,omitempty"`
	Target     string          `json:"target,omitempty"`
	Decision   string          `json:"decision"`
	Reason     string          `json:"reason,omitempty"`
	Bytes      int64           `json:"bytes,omitempty"`
	Metadata   json.RawMessage `json:"metadata,omitempty"`
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

// GetHashtag returns interactions whose content contains a hashtag.
func (db *DB) GetHashtag(tag string, limit, offset int) ([]Interaction, error) {
	rows, err := db.Query(
		`SELECT id, timestamp, data, type, thread_id, agent_id
		 FROM interactions
		 WHERE json_extract(data, '$.content') LIKE ?
		 ORDER BY id DESC LIMIT ? OFFSET ?`,
		"%#"+tag+"%", limit, offset)
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

// UserProfile stores persisted user display metadata.
type UserProfile struct {
	Name             string `json:"name"`
	AvatarURL        string `json:"avatar_url,omitempty"`
	AvatarBackground string `json:"avatar_background,omitempty"`
}

// GetUserProfile returns the persisted user profile, or sensible defaults.
func (db *DB) GetUserProfile() (UserProfile, error) {
	profile := UserProfile{Name: "You"}
	var raw string
	err := db.QueryRow("SELECT value FROM settings WHERE key = ?", "user_profile").Scan(&raw)
	if err == sql.ErrNoRows {
		return profile, nil
	}
	if err != nil {
		return profile, err
	}
	if raw != "" {
		if err := json.Unmarshal([]byte(raw), &profile); err != nil {
			return UserProfile{Name: "You"}, err
		}
	}
	profile.Name = strings.TrimSpace(profile.Name)
	if profile.Name == "" {
		profile.Name = "You"
	}
	profile.AvatarURL = strings.TrimSpace(profile.AvatarURL)
	profile.AvatarBackground = strings.TrimSpace(profile.AvatarBackground)
	return profile, nil
}

// SetUserProfile stores the user profile in the settings table.
func (db *DB) SetUserProfile(profile UserProfile) error {
	profile.Name = strings.TrimSpace(profile.Name)
	if profile.Name == "" {
		profile.Name = "You"
	}
	profile.AvatarURL = strings.TrimSpace(profile.AvatarURL)
	profile.AvatarBackground = strings.TrimSpace(profile.AvatarBackground)
	payload, err := json.Marshal(profile)
	if err != nil {
		return err
	}
	_, err = db.Exec(`
		INSERT INTO settings (key, value, updated_at)
		VALUES (?, ?, datetime('now'))
		ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
	`, "user_profile", string(payload))
	return err
}

// ThreadBackend stores a thread's current backend affinity.
type ThreadBackend struct {
	ThreadID          int64           `json:"thread_id"`
	Backend           BackendMetadata `json:"backend"`
	BackendGeneration int             `json:"backend_generation"`
}

// GetThreadBackend returns the current backend affinity for a thread.
func (db *DB) GetThreadBackend(threadID int64) (*ThreadBackend, error) {
	var raw string
	var generation int
	err := db.QueryRow(
		"SELECT backend, backend_generation FROM thread_metadata WHERE thread_id = ?",
		threadID,
	).Scan(&raw, &generation)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var backend BackendMetadata
	if err := json.Unmarshal([]byte(raw), &backend); err != nil {
		return nil, err
	}
	return &ThreadBackend{ThreadID: threadID, Backend: backend, BackendGeneration: generation}, nil
}

// SetThreadBackend stores backend affinity for a thread. If changed is true,
// callers should record a timeline backend-switch event.
func (db *DB) SetThreadBackend(threadID int64, backend BackendMetadata) (*ThreadBackend, bool, error) {
	current, err := db.GetThreadBackend(threadID)
	if err != nil {
		return nil, false, err
	}
	generation := 1
	changed := false
	if current != nil {
		generation = current.BackendGeneration
		if current.Backend.ID != backend.ID {
			generation++
			changed = true
		}
	} else {
		changed = true
	}
	backend.ThreadBackendGeneration = generation
	payload, err := json.Marshal(backend)
	if err != nil {
		return nil, false, err
	}
	_, err = db.Exec(`
		INSERT INTO thread_metadata (thread_id, backend, backend_generation, updated_at)
		VALUES (?, ?, ?, datetime('now'))
		ON CONFLICT(thread_id) DO UPDATE SET
			backend = excluded.backend,
			backend_generation = excluded.backend_generation,
			updated_at = datetime('now')
	`, threadID, string(payload), generation)
	if err != nil {
		return nil, false, err
	}
	return &ThreadBackend{ThreadID: threadID, Backend: backend, BackendGeneration: generation}, changed, nil
}

// ── Local service audit ──────────────────────────────────────────

// InsertLocalServiceAudit stores a sanitized local-service audit event.
func (db *DB) InsertLocalServiceAudit(a LocalServiceAudit) (int64, error) {
	a.Type = strings.TrimSpace(a.Type)
	if a.Type == "" {
		a.Type = "acp_local_service"
	}
	a.Method = strings.TrimSpace(a.Method)
	a.Decision = strings.TrimSpace(a.Decision)
	if a.Method == "" || a.Decision == "" {
		return 0, fmt.Errorf("method and decision are required")
	}
	metadata := ""
	if len(a.Metadata) > 0 {
		if !json.Valid(a.Metadata) {
			return 0, fmt.Errorf("metadata must be valid JSON")
		}
		metadata = string(a.Metadata)
	}
	result, err := db.Exec(`
		INSERT INTO local_service_audit (
			type, provider_id, session_id, method, request_id, target,
			decision, reason, bytes, metadata
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULLIF(?, ''))
	`, a.Type, a.ProviderID, a.SessionID, a.Method, a.RequestID, a.Target, a.Decision, a.Reason, a.Bytes, metadata)
	if err != nil {
		return 0, err
	}
	return result.LastInsertId()
}

// GetLocalServiceAudit retrieves one local-service audit event.
func (db *DB) GetLocalServiceAudit(id int64) (*LocalServiceAudit, error) {
	row := db.QueryRow(`
		SELECT id, timestamp, type, provider_id, session_id, method, request_id,
		       target, decision, reason, bytes, metadata
		FROM local_service_audit WHERE id = ?
	`, id)
	return scanLocalServiceAudit(row)
}

// GetLocalServiceAudits retrieves recent local-service audit events.
func (db *DB) GetLocalServiceAudits(limit int) ([]LocalServiceAudit, error) {
	if limit <= 0 {
		limit = 50
	}
	rows, err := db.Query(`
		SELECT id, timestamp, type, provider_id, session_id, method, request_id,
		       target, decision, reason, bytes, metadata
		FROM local_service_audit
		ORDER BY id DESC LIMIT ?
	`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var audits []LocalServiceAudit
	for rows.Next() {
		audit, err := scanLocalServiceAuditRow(rows)
		if err != nil {
			return nil, err
		}
		audits = append(audits, *audit)
	}
	return audits, rows.Err()
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

func scanLocalServiceAudit(row *sql.Row) (*LocalServiceAudit, error) {
	a := &LocalServiceAudit{}
	var providerID, sessionID, requestID, target, reason, metadata sql.NullString
	err := row.Scan(&a.ID, &a.Timestamp, &a.Type, &providerID, &sessionID, &a.Method, &requestID, &target, &a.Decision, &reason, &a.Bytes, &metadata)
	if err != nil {
		return nil, err
	}
	copyLocalServiceAuditNulls(a, providerID, sessionID, requestID, target, reason, metadata)
	return a, nil
}

func scanLocalServiceAuditRow(rows *sql.Rows) (*LocalServiceAudit, error) {
	a := &LocalServiceAudit{}
	var providerID, sessionID, requestID, target, reason, metadata sql.NullString
	if err := rows.Scan(&a.ID, &a.Timestamp, &a.Type, &providerID, &sessionID, &a.Method, &requestID, &target, &a.Decision, &reason, &a.Bytes, &metadata); err != nil {
		return nil, err
	}
	copyLocalServiceAuditNulls(a, providerID, sessionID, requestID, target, reason, metadata)
	return a, nil
}

func copyLocalServiceAuditNulls(a *LocalServiceAudit, providerID, sessionID, requestID, target, reason, metadata sql.NullString) {
	if providerID.Valid {
		a.ProviderID = providerID.String
	}
	if sessionID.Valid {
		a.SessionID = sessionID.String
	}
	if requestID.Valid {
		a.RequestID = requestID.String
	}
	if target.Valid {
		a.Target = target.String
	}
	if reason.Valid {
		a.Reason = reason.String
	}
	if metadata.Valid {
		a.Metadata = json.RawMessage(metadata.String)
	}
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

// BackendMetadata records rich per-turn backend provenance without adding
// rigid generated columns for every future provider-specific field.
type BackendMetadata struct {
	ID                      string `json:"id"`
	Family                  string `json:"family,omitempty"`
	Transport               string `json:"transport,omitempty"`
	Label                   string `json:"label,omitempty"`
	Model                   string `json:"model,omitempty"`
	Mode                    string `json:"mode,omitempty"`
	ProviderSessionID       string `json:"provider_session_id,omitempty"`
	ProviderTurnID          string `json:"provider_turn_id,omitempty"`
	ThreadBackendGeneration int    `json:"thread_backend_generation,omitempty"`
}

// BackendSwitch records an explicit backend handoff point in a thread.
type BackendSwitch struct {
	From                    string `json:"from,omitempty"`
	To                      string `json:"to"`
	ThreadBackendGeneration int    `json:"thread_backend_generation"`
}

// InteractionData is the typed payload structure stored as JSON.
type InteractionData struct {
	Type          string           `json:"type"`               // "user_message", "agent_response", "system"
	Content       string           `json:"content"`            // text content
	AgentID       string           `json:"agent_id,omitempty"` // which agent responded
	ThreadID      *int64           `json:"thread_id,omitempty"`
	MediaIDs      []int64          `json:"media_ids,omitempty"`
	Backend       *BackendMetadata `json:"backend,omitempty"`
	BackendSwitch *BackendSwitch   `json:"backend_switch,omitempty"`
	// Agent-specific fields
	Model  string `json:"model,omitempty"`
	Tokens *int   `json:"tokens,omitempty"`
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
