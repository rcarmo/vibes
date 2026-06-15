package acp

import (
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

func TestWriteTextPermissionRequestShape(t *testing.T) {
	plan := WriteTextPlan{
		Root:         "/workspace",
		ResolvedPath: "/workspace/app/config.json",
		Bytes:        18,
		Exists:       true,
		Overwrite:    true,
	}
	req := writeTextPermissionRequest("copilot", "session-1", "request-1", plan, "secret\nvalue")
	if req.ID != "request-1" || req.Method != "fs/write_text_file" {
		t.Fatalf("unexpected request identity: %#v", req)
	}
	if !strings.Contains(req.Title, "overwrite") || !strings.Contains(req.Title, plan.ResolvedPath) {
		t.Fatalf("title does not call out overwrite target: %q", req.Title)
	}
	if len(req.Options) != 2 || req.Options[0].ID != writeTextPermissionAllowOnce || req.Options[1].ID != writeTextPermissionReject {
		t.Fatalf("unexpected options: %#v", req.Options)
	}
	if req.Raw["content"] != nil {
		t.Fatalf("permission request must not include full content: %#v", req.Raw)
	}
	if req.Raw["operation"] != "overwrite" || req.Raw["overwrite"] != true || req.Raw["bytes"] != int64(18) {
		t.Fatalf("unexpected raw metadata: %#v", req.Raw)
	}
	preview, _ := req.Raw["contentPreview"].(string)
	if strings.Contains(preview, "\n") {
		t.Fatalf("preview should escape control characters: %q", preview)
	}
	hash, _ := req.Raw["contentSha256"].(string)
	if len(hash) != 64 {
		t.Fatalf("sha256 hash length = %d", len(hash))
	}
}

func TestWriteTextPermissionRequestPreviewTruncates(t *testing.T) {
	plan := WriteTextPlan{Root: "/workspace", ResolvedPath: "/workspace/new.txt", Bytes: 512}
	req := writeTextPermissionRequest("codex", "session-1", "request-2", plan, strings.Repeat("a", writeTextPreviewMaxRunes+1))
	if req.Raw["operation"] != "create" || req.Raw["overwrite"] != false {
		t.Fatalf("unexpected create metadata: %#v", req.Raw)
	}
	if req.Raw["previewTruncated"] != true {
		t.Fatalf("previewTruncated = %#v", req.Raw["previewTruncated"])
	}
}

func TestResolveWriteTextPermissionDecision(t *testing.T) {
	plan := WriteTextPlan{ResolvedPath: "/workspace/new.txt", Bytes: 5}
	cases := []struct {
		name          string
		selected      string
		err           error
		allowed       bool
		auditDecision string
		reason        string
	}{
		{name: "approved", selected: writeTextPermissionAllowOnce, allowed: true, auditDecision: "approved", reason: "user_approved"},
		{name: "denied", selected: writeTextPermissionReject, allowed: false, auditDecision: "denied", reason: "user_denied"},
		{name: "timeout", selected: "cancelled", allowed: false, auditDecision: "timeout", reason: "permission_timeout"},
		{name: "empty timeout", selected: "", allowed: false, auditDecision: "timeout", reason: "permission_timeout"},
		{name: "handler error", err: errors.New("broker down"), allowed: false, auditDecision: "error", reason: "permission_error"},
		{name: "broad auto approve rejected", selected: "approve", allowed: false, auditDecision: "denied", reason: "invalid_permission_option"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			decision := resolveWriteTextPermissionDecision("copilot", "session-1", "request-1", plan, tc.selected, tc.err)
			if decision.Allowed != tc.allowed || decision.Reason != tc.reason {
				t.Fatalf("decision = %#v", decision)
			}
			if decision.AuditEvent.Decision != tc.auditDecision || decision.AuditEvent.Reason != tc.reason {
				t.Fatalf("audit = %#v", decision.AuditEvent)
			}
			if decision.AuditEvent.Method != "fs/write_text_file" || decision.AuditEvent.Target != plan.ResolvedPath || decision.AuditEvent.Bytes != plan.Bytes {
				t.Fatalf("audit event lost write metadata: %#v", decision.AuditEvent)
			}
		})
	}
}

func TestLocalServiceAuditRecorderNoopAndInstalledRecorder(t *testing.T) {
	p := New(Config{})
	event := writePlanAuditEvent("copilot", "session-1", "request-1", WriteTextPlan{ResolvedPath: "/workspace/new.txt", Bytes: 4}, "denied", "user_denied")
	p.recordLocalServiceAudit(event) // no recorder: should not panic

	var recorded []LocalServiceAuditEvent
	p.SetLocalServiceAuditRecorder(LocalServiceAuditRecorderFunc(func(event LocalServiceAuditEvent) {
		recorded = append(recorded, event)
	}))
	p.recordLocalServiceAudit(event)
	if len(recorded) != 1 || recorded[0].Decision != "denied" {
		t.Fatalf("recorded = %#v", recorded)
	}
}

func TestWriteAuditEventContainsNoContent(t *testing.T) {
	plan := WriteTextPlan{ResolvedPath: "/workspace/new.txt", Bytes: 12}
	event := writePlanAuditEvent("copilot", "session-1", "request-1", plan, "timeout", "permission_timeout")
	data, err := json.Marshal(event)
	if err != nil {
		t.Fatal(err)
	}
	serialized := string(data)
	for _, forbidden := range []string{"content", "preview", "secret", "environment"} {
		if strings.Contains(serialized, forbidden) {
			t.Fatalf("audit event leaked %q: %s", forbidden, serialized)
		}
	}
}
