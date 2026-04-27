package db

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"
)

// FuzzInsertInteraction ensures InsertInteraction never panics on arbitrary JSON.
func FuzzInsertInteraction(f *testing.F) {
	f.Add(`{"type":"user_message","content":"hello"}`)
	f.Add(`{"type":"agent_response","content":"world","agent_id":"test"}`)
	f.Add(`{}`)
	f.Add(`{"content":""}`)
	f.Add(`{"type":"","content":"` + strings.Repeat("a", 10000) + `"}`)

	f.Fuzz(func(t *testing.T, data string) {
		// Skip invalid JSON
		if !json.Valid([]byte(data)) {
			t.Skip("invalid JSON")
		}

		db, err := Open(filepath.Join(t.TempDir(), "fuzz.db"))
		if err != nil {
			t.Skip("open failed")
		}
		defer db.Close()

		// Should never panic
		id, err := db.InsertInteraction(json.RawMessage(data))
		if err != nil {
			return // valid error
		}

		// If insert succeeded, get should work
		got, err := db.GetInteraction(id)
		if err != nil {
			t.Errorf("GetInteraction after successful insert: %v", err)
		}
		if got == nil {
			t.Error("GetInteraction returned nil after successful insert")
		}
	})
}

// FuzzSearchInteractions ensures search never panics on arbitrary queries.
func FuzzSearchInteractions(f *testing.F) {
	f.Add("hello")
	f.Add("hello world")
	f.Add("OR AND NOT")
	f.Add("")
	f.Add("*")
	f.Add(`"quoted"`)
	f.Add(strings.Repeat("x", 1000))

	f.Fuzz(func(t *testing.T, query string) {
		if query == "" {
			t.Skip("empty query")
		}

		db, err := Open(filepath.Join(t.TempDir(), "fuzz.db"))
		if err != nil {
			t.Skip("open failed")
		}
		defer db.Close()

		// Insert something to search against
		data, _ := MarshalInteraction(NewUserMessage("the quick brown fox", nil))
		db.InsertInteraction(data)

		// Should never panic
		_, _ = db.SearchInteractions(query, 10, 0)
	})
}

// FuzzMatchGlob ensures glob matching never panics.
func FuzzMatchGlob(f *testing.F) {
	f.Add("*", "anything")
	f.Add("Run *", "Run command")
	f.Add("", "")
	f.Add("a*b", "aXb")
	f.Add(strings.Repeat("*", 100), strings.Repeat("x", 100))

	f.Fuzz(func(t *testing.T, pattern, value string) {
		// Should never panic
		_ = matchGlob(pattern, value)
	})
}
