package routes

import (
	"os"
	"testing"
)

func TestTurnManager(t *testing.T) {
	tm := NewTurnManager()

	// Update adds content
	tm.Update("turn-1", "draft", "Hello ")
	tm.Update("turn-1", "draft", "world")
	tm.Update("turn-1", "thought", "thinking...")

	tc := tm.Get("turn-1")
	if tc.Draft != "Hello world" {
		t.Errorf("Draft = %q, want 'Hello world'", tc.Draft)
	}
	if tc.Thought != "thinking..." {
		t.Errorf("Thought = %q", tc.Thought)
	}

	// Unknown turn returns empty
	tc2 := tm.Get("nonexistent")
	if tc2.Draft != "" {
		t.Errorf("nonexistent turn Draft = %q, want empty", tc2.Draft)
	}

	// Panel state
	tm.SetPanel("turn-1", "draft", true)
	tm.SetPanel("turn-1", "thought", false)
	panels := tm.GetPanels("turn-1")
	if !panels["draft"] {
		t.Error("draft panel should be expanded")
	}
	if panels["thought"] {
		t.Error("thought panel should be collapsed")
	}

	// Clear
	tm.Clear("turn-1")
	tc3 := tm.Get("turn-1")
	if tc3.Draft != "" {
		t.Error("after clear, Draft should be empty")
	}
}

func TestLoadActionsFileNotFound(t *testing.T) {
	cfg, err := LoadActions("/nonexistent/path.json")
	if err != nil {
		t.Fatalf("expected nil error for missing file, got: %v", err)
	}
	if len(cfg.Endpoints) != 0 {
		t.Errorf("expected empty endpoints, got %d", len(cfg.Endpoints))
	}
}

func TestLoadActionsValid(t *testing.T) {
	dir := t.TempDir()
	path := dir + "/endpoints.json"
	data := []byte(`{"endpoints":{"summarize":{"description":"Summarize","prompt":"Summarize this","params":["url"]}}}`)
	if err := writeTestFile(path, data); err != nil {
		t.Fatal(err)
	}

	cfg, err := LoadActions(path)
	if err != nil {
		t.Fatalf("LoadActions: %v", err)
	}
	if len(cfg.Endpoints) != 1 {
		t.Errorf("expected 1 endpoint, got %d", len(cfg.Endpoints))
	}
	if cfg.Endpoints["summarize"].Prompt != "Summarize this" {
		t.Errorf("prompt = %q", cfg.Endpoints["summarize"].Prompt)
	}
}

func writeTestFile(path string, data []byte) error {
	return os.WriteFile(path, data, 0o644)
}

// Tests for #13 — agent queue, models, respond endpoints

func TestFollowUpQueueListEmpty(t *testing.T) {
	q := NewFollowUpQueue()
	items := q.List()
	if len(items) != 0 {
		t.Errorf("expected empty, got %d", len(items))
	}
}

func TestFollowUpQueueRoundTrip(t *testing.T) {
	q := NewFollowUpQueue()
	q.Add("msg1", "queue")
	q.Add("msg2", "queue")

	items := q.List()
	if len(items) != 2 {
		t.Fatalf("expected 2, got %d", len(items))
	}

	item, ok := q.Pop()
	if !ok || item.Content != "msg1" {
		t.Errorf("Pop = %v, %v", item, ok)
	}

	// After pop, 1 item left
	if len(q.List()) != 1 {
		t.Errorf("expected 1 after pop")
	}
}

func TestFollowUpQueueSteer(t *testing.T) {
	q := NewFollowUpQueue()
	item := q.Add("steer me", "queue")
	q.PromoteToSteer(item.RowID)

	items := q.List()
	if items[0].Mode != "steer" {
		t.Errorf("mode = %q, want steer", items[0].Mode)
	}
}

func TestPermissionBrokerRespond(t *testing.T) {
	pb := &PermissionBroker{
		pending: make(map[string]*PermissionRequest),
	}

	req := &PermissionRequest{
		ID:   "req-1",
		done: make(chan string, 1),
	}
	pb.pending["req-1"] = req

	ok := pb.Respond("req-1", "approve")
	if !ok {
		t.Error("Respond returned false")
	}

	outcome := <-req.done
	if outcome != "approve" {
		t.Errorf("outcome = %q", outcome)
	}

	// Double-respond should fail
	ok = pb.Respond("req-1", "deny")
	if ok {
		t.Error("second Respond should return false")
	}
}
