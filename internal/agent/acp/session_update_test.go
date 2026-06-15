package acp

import (
	"encoding/json"
	"testing"

	"github.com/rcarmo/vibes/internal/agent"
)

func TestApplySessionUpdateMetadata(t *testing.T) {
	p := New(Config{})
	p.setStatusProviderState("idle", "model", 0)
	p.applySessionUpdateMetadata(map[string]interface{}{
		"currentMode": "plan",
		"usage": map[string]interface{}{
			"used":  250.0,
			"total": 1000.0,
		},
		"availableCommands": []interface{}{map[string]interface{}{"id": "explain"}},
	})
	metadata := p.SessionMetadata()
	if metadata.CurrentMode != "plan" || len(metadata.Commands) != 1 || metadata.Commands[0]["id"] != "explain" {
		t.Fatalf("metadata not applied: %#v", metadata)
	}
	if got := p.Status().ContextPct; got != 0.25 {
		t.Fatalf("context pct = %v", got)
	}
}

func TestRouteSessionUpdateEmitsSessionUpdateAndTypedStatus(t *testing.T) {
	p := New(Config{})
	payload := map[string]interface{}{
		"update": map[string]interface{}{
			"sessionUpdate": "tool_call_update",
			"title":         "Read file",
			"status":        "Running",
			"percent":       50.0,
		},
	}
	raw, _ := json.Marshal(payload)
	p.routeSessionUpdate(raw)

	first := <-p.Events()
	if first.Type != "session_update" {
		t.Fatalf("first event = %#v", first)
	}
	data, ok := first.Data.(map[string]interface{})
	if !ok || data["kind"] != "tool_call_update" || data["context_pct"] != 0.5 {
		t.Fatalf("session update data = %#v", first.Data)
	}
	second := <-p.Events()
	if second.Type != "status" {
		t.Fatalf("second event = %#v", second)
	}
	status, ok := second.Data.(map[string]interface{})
	if !ok || status["type"] != "tool_status" || status["title"] != "Read file" || status["status"] != "Running" {
		t.Fatalf("status event data = %#v", second.Data)
	}
}

func (p *Provider) setStatusProviderState(state, model string, contextPct float64) {
	p.setStatus(agentStatus(state, model, contextPct))
}

func agentStatus(state, model string, contextPct float64) agent.ProviderStatus {
	return agent.ProviderStatus{State: state, Model: model, ContextPct: contextPct}
}
