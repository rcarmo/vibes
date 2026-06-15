package routes

import (
	"path/filepath"
	"testing"
	"time"

	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/agent/acp"
	"github.com/rcarmo/vibes/internal/db"
	"github.com/rcarmo/vibes/internal/server/sse"
)

func TestACPOptionsToRouteOptions(t *testing.T) {
	options := acpOptionsToRouteOptions([]acp.PermissionOption{
		{ID: "allow", Name: "Allow once", Kind: "allow_once"},
		{ID: "deny"},
	})
	if len(options) != 2 {
		t.Fatalf("len = %d", len(options))
	}
	if options[0].ID != "allow" || options[0].Label != "Allow once (allow_once)" {
		t.Fatalf("first option = %#v", options[0])
	}
	if options[1].ID != "deny" || options[1].Label != "deny" {
		t.Fatalf("second option = %#v", options[1])
	}
}

func TestWireACPLocalServicePermissionBrokerApproveDenyAudit(t *testing.T) {
	cases := []struct {
		name          string
		response      string
		allowed       bool
		auditDecision string
	}{
		{name: "approve", response: "allow_once", allowed: true, auditDecision: "approved"},
		{name: "deny", response: "reject", allowed: false, auditDecision: "denied"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			provider, broker, client := wiredACPProviderForTest(t, time.Second)
			plan := acp.WriteTextPlan{Root: "/workspace", ResolvedPath: "/workspace/new.txt", Bytes: 5}
			decisionCh := make(chan acp.WriteTextPermissionDecision, 1)
			go func() {
				decisionCh <- provider.MediateWriteTextPlan("request-1", plan, "hello")
			}()

			requestEvent := waitForEvent(t, client, "agent_request")
			req, ok := requestEvent.Data.(*PermissionRequest)
			if !ok {
				t.Fatalf("request event data = %#v", requestEvent.Data)
			}
			if req.ID != "request-1" || req.Method != "fs/write_text_file" || len(req.Options) != 2 {
				t.Fatalf("permission request = %#v", req)
			}
			if !broker.Respond("request-1", tc.response) {
				t.Fatal("permission response was not accepted")
			}

			select {
			case decision := <-decisionCh:
				if decision.Allowed != tc.allowed || decision.AuditEvent.Decision != tc.auditDecision {
					t.Fatalf("decision = %#v", decision)
				}
			case <-time.After(time.Second):
				t.Fatal("timed out waiting for decision")
			}

			auditEvent := waitForEvent(t, client, "agent_audit")
			audit, ok := auditEvent.Data.(acp.LocalServiceAuditEvent)
			if !ok {
				t.Fatalf("audit event data = %#v", auditEvent.Data)
			}
			if audit.Method != "fs/write_text_file" || audit.Decision != tc.auditDecision || audit.Target != plan.ResolvedPath || audit.Bytes != plan.Bytes {
				t.Fatalf("audit event = %#v", audit)
			}
		})
	}
}

func TestWireACPLocalServiceBypassesWhitelistAutoApprove(t *testing.T) {
	registry := agent.NewRegistry()
	provider := acp.New(acp.Config{ID: "codex"})
	registry.RegisterWithDescriptor("codex", provider, agent.ProviderDescriptor{ID: "codex", Label: "Codex", Available: true})
	database, err := db.Open(filepath.Join(t.TempDir(), "vibes.db"))
	if err != nil {
		t.Fatalf("db open: %v", err)
	}
	t.Cleanup(func() { database.Close() })
	if err := database.AddWhitelistPattern("fs/write_text_file", "broad write whitelist"); err != nil {
		t.Fatalf("add whitelist: %v", err)
	}
	sseBroker := sse.NewBroker()
	client := sseBroker.Subscribe("test")
	broker := NewPermissionBroker(sseBroker, time.Second, database)
	wireACPPermissionHandlers(registry, broker)

	plan := acp.WriteTextPlan{Root: "/workspace", ResolvedPath: "/workspace/new.txt", Bytes: 5}
	decisionCh := make(chan acp.WriteTextPermissionDecision, 1)
	go func() {
		decisionCh <- provider.MediateWriteTextPlan("request-whitelist", plan, "hello")
	}()

	requestEvent := waitForEvent(t, client, "agent_request")
	if req := requestEvent.Data.(*PermissionRequest); req.ID != "request-whitelist" {
		t.Fatalf("permission request = %#v", req)
	}
	if !broker.Respond("request-whitelist", "reject") {
		t.Fatal("permission response was not accepted")
	}
	select {
	case decision := <-decisionCh:
		if decision.Allowed || decision.AuditEvent.Decision != "denied" {
			t.Fatalf("decision = %#v", decision)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for decision")
	}
}

func TestWireACPLocalServicePermissionBrokerTimeoutAudit(t *testing.T) {
	provider, _, client := wiredACPProviderForTest(t, 20*time.Millisecond)
	plan := acp.WriteTextPlan{Root: "/workspace", ResolvedPath: "/workspace/new.txt", Bytes: 5}
	decisionCh := make(chan acp.WriteTextPermissionDecision, 1)
	go func() {
		decisionCh <- provider.MediateWriteTextPlan("request-timeout", plan, "hello")
	}()

	_ = waitForEvent(t, client, "agent_request")
	select {
	case decision := <-decisionCh:
		if decision.Allowed || decision.AuditEvent.Decision != "timeout" || decision.Reason != "permission_timeout" {
			t.Fatalf("decision = %#v", decision)
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for timeout decision")
	}
	auditEvent := waitForEvent(t, client, "agent_audit")
	audit, ok := auditEvent.Data.(acp.LocalServiceAuditEvent)
	if !ok {
		t.Fatalf("audit event data = %#v", auditEvent.Data)
	}
	if audit.Decision != "timeout" || audit.Reason != "permission_timeout" {
		t.Fatalf("audit event = %#v", audit)
	}
}

func wiredACPProviderForTest(t *testing.T, timeout time.Duration) (*acp.Provider, *PermissionBroker, *sse.Client) {
	t.Helper()
	registry := agent.NewRegistry()
	provider := acp.New(acp.Config{ID: "codex"})
	registry.RegisterWithDescriptor("codex", provider, agent.ProviderDescriptor{ID: "codex", Label: "Codex", Available: true})
	sseBroker := sse.NewBroker()
	client := sseBroker.Subscribe("test")
	broker := NewPermissionBroker(sseBroker, timeout)
	wireACPPermissionHandlers(registry, broker)
	return provider, broker, client
}

func waitForEvent(t *testing.T, client *sse.Client, eventType string) sse.Event {
	t.Helper()
	deadline := time.After(time.Second)
	for {
		select {
		case event := <-client.Events():
			if event.Type == eventType {
				return event
			}
		case <-deadline:
			t.Fatalf("timed out waiting for event %q", eventType)
		}
	}
}
