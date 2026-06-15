package routes

import (
	"context"
	"log"
	"net/http"
	"os/exec"
	"sync"
	"time"

	"github.com/rcarmo/vibes/internal/db"
	"github.com/rcarmo/vibes/internal/server/sse"
)

// PermissionRequest represents a pending agent permission request.
type PermissionRequest struct {
	ID        string      `json:"id"`
	Method    string      `json:"method"`
	Title     string      `json:"title"`
	Options   []Option    `json:"options"`
	Timestamp time.Time   `json:"timestamp"`
	done      chan string // receives the selected option ID
}

// Option is a choice in a permission request.
type Option struct {
	ID    string `json:"id"`
	Label string `json:"label"`
}

// PermissionBroker manages pending permission requests from agents.
type PermissionBroker struct {
	mu          sync.RWMutex
	pending     map[string]*PermissionRequest
	sseBrk      *sse.Broker
	timeout     time.Duration
	whitelistDB *db.DB // for auto-approve (fixes #8)
}

// NewPermissionBroker creates a permission broker.
func NewPermissionBroker(sseBroker *sse.Broker, timeout time.Duration, whitelistDB ...*db.DB) *PermissionBroker {
	pb := &PermissionBroker{
		pending: make(map[string]*PermissionRequest),
		sseBrk:  sseBroker,
		timeout: timeout,
	}
	if len(whitelistDB) > 0 {
		pb.whitelistDB = whitelistDB[0]
	}
	return pb
}

// Request creates a permission request and broadcasts it via SSE.
// Blocks until the user responds or the timeout expires.
// Auto-approves if the method matches a whitelist pattern. (fixes #8)
func (pb *PermissionBroker) Request(id, method, title string, options []Option) (string, error) {
	return pb.request(id, method, title, options, true)
}

// RequestManual creates a permission request while deliberately bypassing broad
// whitelist auto-approval. Use this for high-risk operation-specific prompts.
func (pb *PermissionBroker) RequestManual(id, method, title string, options []Option) (string, error) {
	return pb.request(id, method, title, options, false)
}

func (pb *PermissionBroker) request(id, method, title string, options []Option, allowWhitelist bool) (string, error) {
	// Auto-approve via whitelist
	if allowWhitelist && pb.whitelistDB != nil {
		if ok, _ := pb.whitelistDB.IsWhitelisted(method); ok {
			log.Println("auto-approved:", method)
			// Return the first option (approve) or "approve"
			if len(options) > 0 {
				return options[0].ID, nil
			}
			return "approve", nil
		}
	}

	req := &PermissionRequest{
		ID:        id,
		Method:    method,
		Title:     title,
		Options:   options,
		Timestamp: time.Now(),
		done:      make(chan string, 1),
	}

	pb.mu.Lock()
	pb.pending[id] = req
	pb.mu.Unlock()

	// Broadcast to SSE clients
	pb.sseBrk.Broadcast(sse.Event{
		Type: "agent_request",
		Data: req,
	})

	// Wait for response or timeout
	select {
	case outcome := <-req.done:
		return outcome, nil
	case <-time.After(pb.timeout):
		pb.mu.Lock()
		delete(pb.pending, id)
		pb.mu.Unlock()
		pb.sseBrk.Broadcast(sse.Event{Type: "agent_request_timeout", Data: map[string]string{"id": id}})
		return "cancelled", nil
	}
}

// Respond handles a user's response to a permission request.
func (pb *PermissionBroker) Respond(id, outcome string) bool {
	pb.mu.Lock()
	req, ok := pb.pending[id]
	if ok {
		delete(pb.pending, id)
	}
	pb.mu.Unlock()

	if !ok {
		return false
	}

	req.done <- outcome
	return true
}

// RespondHandler returns an HTTP handler for permission responses.
func (pb *PermissionBroker) RespondHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			RequestID string `json:"request_id"`
			Outcome   string `json:"outcome"` // option ID or "cancelled"
		}
		if err := decodeJSON(r, &req); err != nil {
			jsonError(w, "invalid body", http.StatusBadRequest)
			return
		}
		if req.RequestID == "" || req.Outcome == "" {
			jsonError(w, "request_id and outcome required", http.StatusBadRequest)
			return
		}

		if !pb.Respond(req.RequestID, req.Outcome) {
			jsonError(w, "no pending request with that ID", http.StatusNotFound)
			return
		}

		jsonResp(w, map[string]string{"status": "ok"})
	}
}

// ── Follow-up Queue ──────────────────────────────────────────────

// QueueItem represents a queued follow-up message.
type QueueItem struct {
	RowID   int64  `json:"row_id"`
	Content string `json:"content"`
	Mode    string `json:"mode"` // "queue" or "steer"
}

// FollowUpQueue manages queued messages and steering messages.
type FollowUpQueue struct {
	mu     sync.Mutex
	items  []QueueItem
	nextID int64
}

// NewFollowUpQueue creates an empty queue.
func NewFollowUpQueue() *FollowUpQueue {
	return &FollowUpQueue{}
}

// Add enqueues a follow-up message.
func (q *FollowUpQueue) Add(content, mode string) QueueItem {
	q.mu.Lock()
	defer q.mu.Unlock()
	q.nextID++
	item := QueueItem{RowID: q.nextID, Content: content, Mode: mode}
	q.items = append(q.items, item)
	return item
}

// Remove removes an item by row ID.
func (q *FollowUpQueue) Remove(rowID int64) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	for i, item := range q.items {
		if item.RowID == rowID {
			q.items = append(q.items[:i], q.items[i+1:]...)
			return true
		}
	}
	return false
}

// Pop removes and returns the first item (FIFO).
func (q *FollowUpQueue) Pop() (QueueItem, bool) {
	q.mu.Lock()
	defer q.mu.Unlock()
	if len(q.items) == 0 {
		return QueueItem{}, false
	}
	item := q.items[0]
	q.items = q.items[1:]
	return item, true
}

// List returns all queued items.
func (q *FollowUpQueue) List() []QueueItem {
	q.mu.Lock()
	defer q.mu.Unlock()
	result := make([]QueueItem, len(q.items))
	copy(result, q.items)
	return result
}

// PromoteToSteer changes an item's mode to "steer".
func (q *FollowUpQueue) PromoteToSteer(rowID int64) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	for i := range q.items {
		if q.items[i].RowID == rowID {
			q.items[i].Mode = "steer"
			return true
		}
	}
	return false
}

// ── Shell Execution ──────────────────────────────────────────────

// ExecuteShell runs a shell command with a timeout and returns the output.
func ExecuteShell(command string, timeout time.Duration) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "bash", "-c", command)
	out, err := cmd.CombinedOutput()

	if ctx.Err() == context.DeadlineExceeded {
		return string(out) + "\n[timed out]", nil
	}
	if err != nil {
		return string(out) + "\n[exit: " + err.Error() + "]", nil
	}
	return string(out), nil
}
