package acp

import (
	"errors"
	"testing"
)

func TestRequestPermissionSelected(t *testing.T) {
	p := New(Config{})
	p.SetPermissionHandler(func(req PermissionRequest) (string, error) {
		if req.ID != "tool-1" || req.Method != "read" || req.Title != "Read file?" {
			t.Fatalf("unexpected request: %#v", req)
		}
		if len(req.Options) != 2 || req.Options[0].ID != "allow" || req.Options[1].ID != "deny" {
			t.Fatalf("unexpected options: %#v", req.Options)
		}
		return "allow", nil
	})
	result, err := p.requestPermission(map[string]interface{}{
		"sessionId": "session-1",
		"toolCall": map[string]interface{}{
			"toolCallId": "tool-1",
			"kind":       "read",
			"title":      "Read file?",
		},
		"options": []interface{}{
			map[string]interface{}{"optionId": "allow", "name": "Allow", "kind": "allow_once"},
			map[string]interface{}{"optionId": "deny", "name": "Deny", "kind": "reject"},
		},
	})
	if err != nil {
		t.Fatalf("requestPermission: %v", err)
	}
	outcome := result["outcome"].(map[string]interface{})
	if outcome["outcome"] != "selected" || outcome["optionId"] != "allow" {
		t.Fatalf("outcome = %#v", outcome)
	}
}

func TestRequestPermissionCancelledOnHandlerError(t *testing.T) {
	p := New(Config{})
	p.SetPermissionHandler(func(req PermissionRequest) (string, error) {
		return "", errors.New("timeout")
	})
	result, err := p.requestPermission(map[string]interface{}{
		"sessionId": "session-1",
		"options":   []interface{}{map[string]interface{}{"optionId": "reject", "name": "Reject", "kind": "reject"}},
	})
	if err == nil {
		t.Fatal("expected handler error")
	}
	outcome := result["outcome"].(map[string]interface{})
	if outcome["outcome"] != "cancelled" {
		t.Fatalf("outcome = %#v", outcome)
	}
}

func TestRequestPermissionUnavailableWithoutHandler(t *testing.T) {
	p := New(Config{})
	if _, err := p.requestPermission(map[string]interface{}{}); err == nil {
		t.Fatal("expected unavailable error")
	}
}
