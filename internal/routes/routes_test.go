package routes

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/rcarmo/vibes/internal/db"
)

func testDB(t *testing.T) *db.DB {
	t.Helper()
	d, err := db.Open(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { d.Close() })
	return d
}

func testRouter(t *testing.T) (chi.Router, *db.DB) {
	t.Helper()
	database := testDB(t)
	r := chi.NewRouter()
	r.Route("/timeline", Timeline(database))
	r.Route("/post", Posts(database))
	r.Route("/thread", Threads(database))
	r.Route("/search", Search(database))
	r.Route("/media", Media(database))
	return r, database
}

func doJSON(r chi.Router, method, path string, body interface{}) *httptest.ResponseRecorder {
	var b io.Reader
	if body != nil {
		data, _ := json.Marshal(body)
		b = bytes.NewReader(data)
	}
	req := httptest.NewRequest(method, path, b)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	return w
}

func TestGetTimelineEmpty(t *testing.T) {
	r, _ := testRouter(t)
	w := doJSON(r, "GET", "/timeline", nil)
	if w.Code != 200 {
		t.Fatalf("status = %d, want 200", w.Code)
	}
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	posts := resp["posts"].([]interface{})
	if len(posts) != 0 {
		t.Errorf("expected empty timeline, got %d posts", len(posts))
	}
}

func TestCreateAndGetPost(t *testing.T) {
	r, _ := testRouter(t)

	// Create
	w := doJSON(r, "POST", "/post", map[string]string{"content": "hello world"})
	if w.Code != 201 {
		t.Fatalf("create status = %d, want 201. Body: %s", w.Code, w.Body.String())
	}
	var createResp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &createResp)
	if createResp["id"] == nil {
		t.Fatal("missing id in response")
	}

	// Get timeline
	w = doJSON(r, "GET", "/timeline", nil)
	if w.Code != 200 {
		t.Fatalf("timeline status = %d", w.Code)
	}
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	posts := resp["posts"].([]interface{})
	if len(posts) != 1 {
		t.Errorf("expected 1 post, got %d", len(posts))
	}
}

func TestCreatePostNoContent(t *testing.T) {
	r, _ := testRouter(t)
	w := doJSON(r, "POST", "/post", map[string]string{"content": ""})
	if w.Code != 400 {
		t.Errorf("status = %d, want 400", w.Code)
	}
}

func TestDeletePost(t *testing.T) {
	r, _ := testRouter(t)

	// Create
	w := doJSON(r, "POST", "/post", map[string]string{"content": "to delete"})
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	id := int(resp["id"].(float64))

	// Delete
	w = doJSON(r, "DELETE", "/post/"+itoa(id), nil)
	if w.Code != 204 {
		t.Errorf("delete status = %d, want 204", w.Code)
	}

	// Verify gone
	w = doJSON(r, "GET", "/timeline", nil)
	json.Unmarshal(w.Body.Bytes(), &resp)
	posts := resp["posts"].([]interface{})
	if len(posts) != 0 {
		t.Errorf("expected 0 posts after delete, got %d", len(posts))
	}
}

func TestSearch(t *testing.T) {
	r, _ := testRouter(t)

	doJSON(r, "POST", "/post", map[string]string{"content": "the quick brown fox"})
	doJSON(r, "POST", "/post", map[string]string{"content": "lazy dog sleeping"})

	w := doJSON(r, "GET", "/search?q=fox", nil)
	if w.Code != 200 {
		t.Fatalf("search status = %d", w.Code)
	}
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	posts := resp["posts"].([]interface{})
	if len(posts) != 1 {
		t.Errorf("expected 1 search result, got %d", len(posts))
	}
}

func TestSearchMissingQuery(t *testing.T) {
	r, _ := testRouter(t)
	w := doJSON(r, "GET", "/search", nil)
	if w.Code != 400 {
		t.Errorf("status = %d, want 400", w.Code)
	}
}

func TestThread(t *testing.T) {
	r, _ := testRouter(t)

	// Create parent
	w := doJSON(r, "POST", "/post", map[string]string{"content": "parent"})
	var resp map[string]interface{}
	json.Unmarshal(w.Body.Bytes(), &resp)
	parentID := int64(resp["id"].(float64))

	// Create reply
	w = doJSON(r, "POST", "/thread", map[string]interface{}{
		"thread_id": parentID,
		"content":   "reply",
	})
	if w.Code != 201 {
		t.Fatalf("reply status = %d, body: %s", w.Code, w.Body.String())
	}

	// Get thread
	w = doJSON(r, "GET", "/thread/"+itoa(int(parentID)), nil)
	if w.Code != 200 {
		t.Fatalf("get thread status = %d", w.Code)
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	posts := resp["posts"].([]interface{})
	if len(posts) != 2 {
		t.Errorf("expected 2 posts in thread, got %d", len(posts))
	}
}

func TestWorkspaceTree(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "hello.txt"), []byte("world"), 0o644)
	os.MkdirAll(filepath.Join(dir, "subdir"), 0o755)

	r := chi.NewRouter()
	r.Route("/workspace", Workspace(dir))

	w := httptest.NewRequest("GET", "/workspace/tree", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, w)

	if rec.Code != 200 {
		t.Fatalf("tree status = %d", rec.Code)
	}
	var resp map[string]interface{}
	json.Unmarshal(rec.Body.Bytes(), &resp)
	entries := resp["entries"].([]interface{})
	if len(entries) < 2 {
		t.Errorf("expected at least 2 entries, got %d", len(entries))
	}
}

func TestWorkspaceFileCRUD(t *testing.T) {
	dir := t.TempDir()
	r := chi.NewRouter()
	r.Route("/workspace", Workspace(dir))

	// Create file
	body, _ := json.Marshal(map[string]string{"path": "", "name": "test.txt", "content": "hello"})
	req := httptest.NewRequest("POST", "/workspace/create", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)
	if rec.Code != 201 {
		t.Fatalf("create status = %d, body: %s", rec.Code, rec.Body.String())
	}

	// Read file
	req = httptest.NewRequest("GET", "/workspace/file?path=test.txt", nil)
	rec = httptest.NewRecorder()
	r.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("get file status = %d", rec.Code)
	}
	var resp map[string]interface{}
	json.Unmarshal(rec.Body.Bytes(), &resp)
	if resp["content"] != "hello" {
		t.Errorf("content = %q, want hello", resp["content"])
	}

	// Update file
	body, _ = json.Marshal(map[string]string{"path": "test.txt", "content": "updated"})
	req = httptest.NewRequest("PUT", "/workspace/file", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec = httptest.NewRecorder()
	r.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("put file status = %d", rec.Code)
	}

	// Verify update
	req = httptest.NewRequest("GET", "/workspace/file?path=test.txt", nil)
	rec = httptest.NewRecorder()
	r.ServeHTTP(rec, req)
	json.Unmarshal(rec.Body.Bytes(), &resp)
	if resp["content"] != "updated" {
		t.Errorf("after update content = %q, want updated", resp["content"])
	}

	// Delete
	req = httptest.NewRequest("DELETE", "/workspace/file?path=test.txt", nil)
	rec = httptest.NewRecorder()
	r.ServeHTTP(rec, req)
	if rec.Code != 204 {
		t.Fatalf("delete file status = %d", rec.Code)
	}
}

func TestWorkspacePathTraversal(t *testing.T) {
	dir := t.TempDir()
	r := chi.NewRouter()
	r.Route("/workspace", Workspace(dir))

	req := httptest.NewRequest("GET", "/workspace/file?path=../../etc/passwd", nil)
	rec := httptest.NewRecorder()
	r.ServeHTTP(rec, req)
	// Should return 404 (safePath prevents traversal)
	if rec.Code == 200 {
		t.Error("path traversal should not return 200")
	}
}

func itoa(i int) string {
	return fmt.Sprintf("%d", i)
}
