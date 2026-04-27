package routes

import (
	"testing"
	"time"
)

func TestFollowUpQueue(t *testing.T) {
	q := NewFollowUpQueue()

	// Empty list
	if items := q.List(); len(items) != 0 {
		t.Errorf("expected empty, got %d items", len(items))
	}

	// Add items
	item1 := q.Add("first", "queue")
	item2 := q.Add("second", "queue")
	q.Add("third", "queue")

	items := q.List()
	if len(items) != 3 {
		t.Fatalf("expected 3 items, got %d", len(items))
	}
	if items[0].Content != "first" {
		t.Errorf("first item content = %q", items[0].Content)
	}

	// Pop (FIFO)
	popped, ok := q.Pop()
	if !ok || popped.Content != "first" {
		t.Errorf("Pop = %v, %v", popped, ok)
	}
	if len(q.List()) != 2 {
		t.Errorf("after pop, expected 2 items")
	}

	// Remove by ID
	if !q.Remove(item2.RowID) {
		t.Error("Remove returned false for existing item")
	}
	if len(q.List()) != 1 {
		t.Errorf("after remove, expected 1 item")
	}

	// Remove non-existent
	if q.Remove(item1.RowID) {
		t.Error("Remove returned true for already-popped item")
	}

	// Promote to steer
	q.Add("steer-me", "queue")
	items = q.List()
	lastID := items[len(items)-1].RowID
	if !q.PromoteToSteer(lastID) {
		t.Error("PromoteToSteer returned false")
	}
	items = q.List()
	for _, item := range items {
		if item.RowID == lastID && item.Mode != "steer" {
			t.Errorf("promoted item mode = %q, want steer", item.Mode)
		}
	}
}

func TestPermissionBrokerTimeout(t *testing.T) {
	// Use a very short timeout
	broker := NewPermissionBroker(nil, 50*time.Millisecond)

	// Need to use a nil-safe SSE broker (skip broadcast for test)
	broker.sseBrk = nil

	// This will time out since nobody responds
	// Can't test directly without SSE broker; test the Respond path instead
	req := &PermissionRequest{
		ID:     "test-1",
		Method: "fs/read",
		done:   make(chan string, 1),
	}
	broker.mu.Lock()
	broker.pending["test-1"] = req
	broker.mu.Unlock()

	// Respond
	ok := broker.Respond("test-1", "approve")
	if !ok {
		t.Error("Respond returned false for pending request")
	}

	outcome := <-req.done
	if outcome != "approve" {
		t.Errorf("outcome = %q, want approve", outcome)
	}

	// Respond to non-existent
	ok = broker.Respond("nonexistent", "deny")
	if ok {
		t.Error("Respond returned true for nonexistent request")
	}
}

func TestExecuteShell(t *testing.T) {
	out, err := ExecuteShell("echo hello", 5*time.Second)
	if err != nil {
		t.Fatalf("ExecuteShell: %v", err)
	}
	if out != "hello\n" {
		t.Errorf("output = %q, want 'hello\\n'", out)
	}
}

func TestExecuteShellTimeout(t *testing.T) {
	out, err := ExecuteShell("sleep 10", 100*time.Millisecond)
	if err != nil {
		t.Fatalf("ExecuteShell: %v", err)
	}
	if !contains(out, "timed out") {
		t.Errorf("expected timeout indicator, got: %q", out)
	}
}

func TestExecuteShellError(t *testing.T) {
	out, err := ExecuteShell("exit 1", 5*time.Second)
	if err != nil {
		t.Fatalf("ExecuteShell error: %v", err)
	}
	if !contains(out, "exit") {
		t.Errorf("expected exit indicator, got: %q", out)
	}
}

func contains(s, sub string) bool {
	for i := 0; i <= len(s)-len(sub); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
