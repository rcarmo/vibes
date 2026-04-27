package pi

import (
	"testing"
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

func TestRouteToolEvent(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type": "tool_execution_start",
		"tool": "bash",
	}

	go p.routeEvent(event)

	e := <-p.events
	if e.Type != "status" {
		t.Errorf("event type = %q, want status", e.Type)
	}
}

func TestRouteAgentEnd(t *testing.T) {
	p := New(Config{Command: "pi"})

	event := map[string]interface{}{
		"type": "agent_end",
	}

	go p.routeEvent(event)

	e := <-p.events
	if e.Type != "response" {
		t.Errorf("event type = %q, want response", e.Type)
	}
}
