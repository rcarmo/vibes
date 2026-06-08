package pi

import (
	"testing"

	"github.com/rcarmo/vibes/internal/agent"
)

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

func TestRouteEvent(t *testing.T) {
	p := New(Config{Command: "pi"})

	// Test text_delta routing
	event := map[string]interface{}{
		"type": "message_update",
		"delta": map[string]interface{}{
			"type": "text_delta",
			"text": "hello",
		},
	}

	go p.routeEvent(event)

	e := <-p.events
	if e.Type != "draft" {
		t.Errorf("event type = %q, want draft", e.Type)
	}
}

func TestRouteThinkingDelta(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type": "message_update",
		"delta": map[string]interface{}{
			"type": "thinking_delta",
			"text": "thinking...",
		},
	}

	go p.routeEvent(event)

	e := <-p.events
	if e.Type != "thought" {
		t.Errorf("event type = %q, want thought", e.Type)
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

func TestRouteAgentEnd(t *testing.T) {
	p := New(Config{Command: "pi"})
	p.setStatus(agent.ProviderStatus{State: "busy", Model: "pi"})

	event := map[string]interface{}{
		"type": "agent_end",
	}

	go p.routeEvent(event)

	e := <-p.events
	if e.Type != "response" {
		t.Errorf("event type = %q, want response", e.Type)
	}
	if p.Status().State != "idle" {
		t.Errorf("state = %q, want idle", p.Status().State)
	}
}

func TestRouteResponseUpdatesModel(t *testing.T) {
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
	<-p.events

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
			"context": map[string]interface{}{"percent": 42.0},
		},
	}

	go p.routeEvent(event)
	<-p.events

	status := p.Status()
	if status.Model != "anthropic/claude-test" {
		t.Errorf("model = %q, want anthropic/claude-test", status.Model)
	}
	if status.ContextPct != 0.42 {
		t.Errorf("context = %v, want 0.42", status.ContextPct)
	}
}
