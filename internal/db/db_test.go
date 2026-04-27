package db

import (
	"os"
	"path/filepath"
	"testing"
)

func tempDB(t *testing.T) *DB {
	t.Helper()
	dir := t.TempDir()
	db, err := Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}

func TestOpenAndMigrate(t *testing.T) {
	db := tempDB(t)
	if db == nil {
		t.Fatal("db is nil")
	}
}

func TestInsertAndGetInteraction(t *testing.T) {
	db := tempDB(t)

	data, _ := MarshalInteraction(NewUserMessage("hello world", nil))
	id, err := db.InsertInteraction(data)
	if err != nil {
		t.Fatalf("InsertInteraction: %v", err)
	}
	if id <= 0 {
		t.Errorf("expected id > 0, got %d", id)
	}

	got, err := db.GetInteraction(id)
	if err != nil {
		t.Fatalf("GetInteraction: %v", err)
	}
	if got.Type != "user_message" {
		t.Errorf("Type = %q, want user_message", got.Type)
	}
}

func TestGetTimeline(t *testing.T) {
	db := tempDB(t)

	for i := 0; i < 5; i++ {
		data, _ := MarshalInteraction(NewUserMessage("msg", nil))
		db.InsertInteraction(data)
	}

	posts, err := db.GetTimeline(3, nil)
	if err != nil {
		t.Fatalf("GetTimeline: %v", err)
	}
	if len(posts) != 3 {
		t.Errorf("got %d posts, want 3", len(posts))
	}
	// Should be in reverse order (newest first)
	if posts[0].ID <= posts[1].ID {
		t.Error("timeline should be ordered newest first")
	}
}

func TestGetThread(t *testing.T) {
	db := tempDB(t)

	// Create parent
	parent, _ := MarshalInteraction(NewUserMessage("parent", nil))
	parentID, _ := db.InsertInteraction(parent)

	// Create reply
	reply := InteractionData{Type: "agent_response", Content: "reply", ThreadID: &parentID}
	replyData, _ := MarshalInteraction(reply)
	db.InsertInteraction(replyData)

	thread, err := db.GetThread(parentID)
	if err != nil {
		t.Fatalf("GetThread: %v", err)
	}
	if len(thread) != 2 {
		t.Errorf("got %d posts in thread, want 2", len(thread))
	}
}

func TestSearch(t *testing.T) {
	db := tempDB(t)

	data, _ := MarshalInteraction(NewUserMessage("the quick brown fox jumps", nil))
	db.InsertInteraction(data)

	data2, _ := MarshalInteraction(NewUserMessage("lazy dog sleeping", nil))
	db.InsertInteraction(data2)

	results, err := db.SearchInteractions("fox", 10, 0)
	if err != nil {
		t.Fatalf("SearchInteractions: %v", err)
	}
	if len(results) != 1 {
		t.Errorf("got %d results, want 1", len(results))
	}
}

func TestDeleteInteraction(t *testing.T) {
	db := tempDB(t)

	data, _ := MarshalInteraction(NewUserMessage("to delete", nil))
	id, _ := db.InsertInteraction(data)

	if err := db.DeleteInteraction(id, false); err != nil {
		t.Fatalf("DeleteInteraction: %v", err)
	}

	_, err := db.GetInteraction(id)
	if err == nil {
		t.Error("expected error after delete")
	}
}

func TestDeleteCascade(t *testing.T) {
	db := tempDB(t)

	parent, _ := MarshalInteraction(NewUserMessage("parent", nil))
	parentID, _ := db.InsertInteraction(parent)

	reply := InteractionData{Type: "agent_response", Content: "child", ThreadID: &parentID}
	replyData, _ := MarshalInteraction(reply)
	db.InsertInteraction(replyData)

	if err := db.DeleteInteraction(parentID, true); err != nil {
		t.Fatalf("DeleteInteraction cascade: %v", err)
	}

	thread, _ := db.GetThread(parentID)
	if len(thread) != 0 {
		t.Errorf("cascade should have deleted all, got %d", len(thread))
	}
}

func TestMedia(t *testing.T) {
	db := tempDB(t)

	id, err := db.InsertMedia("test.png", "image/png", []byte("fakeimage"), []byte("thumb"), nil)
	if err != nil {
		t.Fatalf("InsertMedia: %v", err)
	}

	media, err := db.GetMedia(id)
	if err != nil {
		t.Fatalf("GetMedia: %v", err)
	}
	if media.Filename != "test.png" {
		t.Errorf("Filename = %q, want test.png", media.Filename)
	}
	if string(media.Data) != "fakeimage" {
		t.Error("data mismatch")
	}
	if string(media.Thumbnail) != "thumb" {
		t.Error("thumbnail mismatch")
	}
}

func TestWhitelist(t *testing.T) {
	db := tempDB(t)

	db.AddWhitelistPattern("Run command", "auto-approve")
	db.AddWhitelistPattern("Read file", "")

	patterns, _ := db.GetWhitelist()
	if len(patterns) != 2 {
		t.Errorf("got %d patterns, want 2", len(patterns))
	}

	ok, _ := db.IsWhitelisted("Run command")
	if !ok {
		t.Error("expected Run command to be whitelisted")
	}

	ok, _ = db.IsWhitelisted("Write file")
	if ok {
		t.Error("expected Write file to NOT be whitelisted")
	}

	db.RemoveWhitelistPattern("Run command")
	patterns, _ = db.GetWhitelist()
	if len(patterns) != 1 {
		t.Errorf("after remove got %d, want 1", len(patterns))
	}
}

func TestMatchGlob(t *testing.T) {
	tests := []struct {
		pattern string
		value   string
		want    bool
	}{
		{"*", "anything", true},
		{"Run *", "Run command", true},
		{"Run *", "Read file", false},
		{"*file", "Read file", true},
		{"exact", "exact", true},
		{"exact", "other", false},
		{"", "", true},
		{"", "x", false},
	}
	for _, tt := range tests {
		got := matchGlob(tt.pattern, tt.value)
		if got != tt.want {
			t.Errorf("matchGlob(%q, %q) = %v, want %v", tt.pattern, tt.value, got, tt.want)
		}
	}
}

func TestReopen(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "reopen.db")

	// First open and insert
	db1, err := Open(path)
	if err != nil {
		t.Fatalf("Open 1: %v", err)
	}
	data, _ := MarshalInteraction(NewUserMessage("persist me", nil))
	db1.InsertInteraction(data)
	db1.Close()

	// Second open and read
	db2, err := Open(path)
	if err != nil {
		t.Fatalf("Open 2: %v", err)
	}
	defer db2.Close()

	posts, _ := db2.GetTimeline(10, nil)
	if len(posts) != 1 {
		t.Errorf("after reopen got %d posts, want 1", len(posts))
	}

	// Suppress unused import
	_ = os.TempDir
}
