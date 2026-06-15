package pi

import (
	"bytes"
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/rcarmo/vibes/internal/agent"
)

type bufferWriteCloser struct{ bytes.Buffer }

func (b *bufferWriteCloser) Close() error { return nil }

func TestNewProvider(t *testing.T) {
	p := New(Config{Command: "pi", WorkDir: "/tmp"})
	if p == nil {
		t.Fatal("New returned nil")
	}
	if p.ID() != "pi" {
		t.Errorf("ID = %q, want pi", p.ID())
	}
	if p.Status().State != "stopped" {
		t.Errorf("initial state = %q, want stopped", p.Status().State)
	}
}

func TestRouteAssistantMessageEventTextDelta(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type": "message_update",
		"assistantMessageEvent": map[string]interface{}{
			"type":  "text_delta",
			"delta": "new protocol",
		},
	}

	go p.routeEvent(event)

	e := <-p.events
	if e.Type != "draft" {
		t.Fatalf("event type = %q, want draft", e.Type)
	}
	data, ok := e.Data.(map[string]string)
	if !ok || data["text"] != "new protocol" {
		t.Fatalf("event data = %#v, want text delta", e.Data)
	}
	if got := p.CollectedDraft(); got != "new protocol" {
		t.Fatalf("collected draft = %q", got)
	}
}

func TestRouteFlatMessageEventTextDelta(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type":  "message_update",
		"kind":  "text_delta",
		"delta": "flat protocol",
	}

	go p.routeEvent(event)

	e := <-p.events
	if e.Type != "draft" {
		t.Fatalf("event type = %q, want draft", e.Type)
	}
	if got := p.CollectedDraft(); got != "flat protocol" {
		t.Fatalf("collected draft = %q", got)
	}
}

func TestRouteAssistantMessageEventThinkingDelta(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type": "message_update",
		"assistantMessageEvent": map[string]interface{}{
			"type":  "thinking_delta",
			"delta": "new thinking",
		},
	}

	go p.routeEvent(event)

	e := <-p.events
	if e.Type != "thought" {
		t.Fatalf("event type = %q, want thought", e.Type)
	}
	data, ok := e.Data.(map[string]string)
	if !ok || data["text"] != "new thinking" {
		t.Fatalf("event data = %#v, want thinking delta", e.Data)
	}
}

func TestRouteMessageEndSnapshotDoesNotDuplicateDraft(t *testing.T) {
	p := New(Config{Command: "pi"})

	p.routeEvent(map[string]interface{}{"type": "message_update", "kind": "text_delta", "delta": "Hello!"})
	<-p.events
	p.routeEvent(map[string]interface{}{"type": "message_end", "content": "Hello!"})

	select {
	case e := <-p.events:
		t.Fatalf("unexpected duplicate event: %#v", e)
	case <-time.After(20 * time.Millisecond):
	}
	if got := p.CollectedDraft(); got != "Hello!" {
		t.Fatalf("CollectedDraft = %q", got)
	}
}

func TestRouteSnapshotMessageUpdatesReplaceDraft(t *testing.T) {
	p := New(Config{Command: "pi"})

	p.routeEvent(map[string]interface{}{"type": "message_update", "content": "Hello"})
	e := <-p.events
	if data := e.Data.(map[string]string); data["mode"] != "replace" {
		t.Fatalf("first snapshot mode = %#v", data)
	}
	p.routeEvent(map[string]interface{}{"type": "message_update", "content": "Hello world"})
	e = <-p.events
	if data := e.Data.(map[string]string); data["mode"] != "replace" {
		t.Fatalf("second snapshot mode = %#v", data)
	}
	if got := p.CollectedDraft(); got != "Hello world" {
		t.Fatalf("CollectedDraft = %q", got)
	}
}

func TestRouteFlatMessageEventThinkingDelta(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type": "message_update",
		"message": map[string]interface{}{
			"kind":    "thinking_delta",
			"content": "flat thinking",
		},
	}

	go p.routeEvent(event)

	e := <-p.events
	if e.Type != "thought" {
		t.Fatalf("event type = %q, want thought", e.Type)
	}
	data, ok := e.Data.(map[string]string)
	if !ok || data["text"] != "flat thinking" {
		t.Fatalf("event data = %#v, want thinking delta", e.Data)
	}
}

func TestRouteToolEvent(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type":     "tool_call",
		"toolName": "bash",
	}

	go p.routeEvent(event)

	e := <-p.events
	if e.Type != "status" {
		t.Errorf("event type = %q, want status", e.Type)
	}
}

func TestRouteAgentEndCompletesWithoutFrontendEvent(t *testing.T) {
	p := New(Config{Command: "pi"})
	p.setStatus(agent.ProviderStatus{State: "busy", Model: "pi"})

	event := map[string]interface{}{
		"type": "agent_end",
	}

	p.routeEvent(event)

	select {
	case e := <-p.events:
		t.Fatalf("unexpected frontend event from agent_end: %#v", e)
	case <-time.After(20 * time.Millisecond):
	}
	if p.Status().State != "idle" {
		t.Errorf("state = %q, want idle", p.Status().State)
	}
}

func TestRouteResponseUpdatesModelAndEmitsModelPayload(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type":    "response",
		"command": "set_model",
		"success": true,
		"data": map[string]interface{}{
			"provider": "openai",
			"id":       "gpt-test",
		},
	}

	go p.routeEvent(event)
	e := <-p.events
	data, ok := e.Data.(map[string]interface{})
	if !ok || data["model"] != "openai/gpt-test" {
		t.Fatalf("event data = %#v, want model payload", e.Data)
	}

	if p.Status().Model != "openai/gpt-test" {
		t.Errorf("model = %q, want openai/gpt-test", p.Status().Model)
	}
}

func TestRouteResponseFailureEmitsError(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type":    "response",
		"command": "set_model",
		"success": false,
		"error":   "nope",
	}

	go p.routeEvent(event)
	e := <-p.events
	if e.Type != "error" {
		t.Fatalf("event type = %q, want error", e.Type)
	}
	if p.Status().State != "error" {
		t.Errorf("state = %q, want error", p.Status().State)
	}
}

func TestCancelCompletesPrompt(t *testing.T) {
	p := New(Config{Command: "pi"})
	p.stdin = &bufferWriteCloser{}

	done := make(chan error, 1)
	go func() {
		done <- p.Prompt(context.Background(), "hello", 1)
	}()

	select {
	case err := <-done:
		t.Fatalf("Prompt returned before cancel: %v", err)
	case <-time.After(20 * time.Millisecond):
	}

	if err := p.Cancel(); err != nil {
		t.Fatalf("Cancel returned error: %v", err)
	}
	<-p.events

	select {
	case err := <-done:
		if err != agent.ErrCancelled {
			t.Fatalf("Prompt error = %v, want ErrCancelled", err)
		}
	case <-time.After(time.Second):
		t.Fatal("Prompt did not return after cancel")
	}
}

func TestPromptWaitsForAgentEndAndCollectsDraft(t *testing.T) {
	p := New(Config{Command: "pi"})
	p.stdin = &bufferWriteCloser{}

	done := make(chan error, 1)
	go func() {
		done <- p.Prompt(context.Background(), "hello", 1)
	}()

	select {
	case err := <-done:
		t.Fatalf("Prompt returned before agent_end: %v", err)
	case <-time.After(20 * time.Millisecond):
	}

	p.routeEvent(map[string]interface{}{"type": "message_update", "kind": "text_delta", "delta": "final text"})
	<-p.events
	p.routeEvent(map[string]interface{}{"type": "agent_end"})

	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("Prompt returned error: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("Prompt did not return after agent_end")
	}
	if got := p.CollectedDraft(); got != "final text" {
		t.Fatalf("CollectedDraft = %q", got)
	}
}

func TestAvailableModelsUsesPiModelCatalog(t *testing.T) {
	p := New(Config{Command: "pi"})
	stdin := &bufferWriteCloser{}
	p.stdin = stdin

	done := make(chan []string, 1)
	errs := make(chan error, 1)
	go func() {
		models, err := p.AvailableModels(context.Background())
		if err != nil {
			errs <- err
			return
		}
		done <- models
	}()

	deadline := time.Now().Add(time.Second)
	for stdin.Len() == 0 && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	var req map[string]interface{}
	if err := json.Unmarshal(stdin.Bytes(), &req); err != nil {
		t.Fatalf("request json: %v", err)
	}
	id := req["id"].(string)
	if req["type"] != "get_available_models" {
		t.Fatalf("request = %#v", req)
	}
	p.routeEvent(map[string]interface{}{
		"type":    "response",
		"id":      id,
		"command": "get_available_models",
		"success": true,
		"data": map[string]interface{}{
			"models": []interface{}{
				map[string]interface{}{"provider": "openai", "id": "gpt-test"},
				"anthropic/claude-test",
			},
		},
	})
	<-p.events

	select {
	case err := <-errs:
		t.Fatalf("AvailableModels error: %v", err)
	case models := <-done:
		want := []string{"openai/gpt-test", "anthropic/claude-test"}
		if len(models) != len(want) || models[0] != want[0] || models[1] != want[1] {
			t.Fatalf("models = %#v, want %#v", models, want)
		}
	case <-time.After(time.Second):
		t.Fatal("AvailableModels timed out")
	}
}

func TestRouteThinkingResponseEmitsThinkingPayload(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type":    "response",
		"command": "set_thinking_level",
		"success": true,
		"data": map[string]interface{}{
			"level": "high",
		},
	}

	go p.routeEvent(event)
	e := <-p.events
	data, ok := e.Data.(map[string]interface{})
	if !ok || data["thinking_level"] != "high" || data["supports_thinking"] != true {
		t.Fatalf("event data = %#v, want thinking payload", e.Data)
	}
}

func TestRouteStateResponseUpdatesContext(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type":    "response",
		"command": "get_state",
		"success": true,
		"data": map[string]interface{}{
			"model": map[string]interface{}{
				"provider": "anthropic",
				"id":       "claude-test",
			},
			"thinkingLevel": "medium",
			"context":       map[string]interface{}{"percent": 42.0},
		},
	}

	go p.routeEvent(event)
	e := <-p.events
	data, ok := e.Data.(map[string]interface{})
	if !ok || data["model"] != "anthropic/claude-test" || data["thinking_level"] != "medium" || data["context_pct"] != 0.42 {
		t.Fatalf("event data = %#v, want state payload", e.Data)
	}

	status := p.Status()
	if status.Model != "anthropic/claude-test" {
		t.Errorf("model = %q, want anthropic/claude-test", status.Model)
	}
	if status.ContextPct != 0.42 {
		t.Errorf("context = %v, want 0.42", status.ContextPct)
	}
}
