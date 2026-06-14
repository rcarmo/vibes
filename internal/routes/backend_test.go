package routes

import (
	"encoding/json"
	"testing"

	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/db"
)

func TestSwitchThreadBackendIncrementsGeneration(t *testing.T) {
	database, err := db.Open(t.TempDir() + "/test.db")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()

	registry := agent.NewRegistry()
	registry.AddDescriptor(agent.ProviderDescriptor{
		ID:        "pi",
		Label:     "Pi",
		Family:    "pi",
		Transport: "pi-rpc",
		Available: true,
	})
	registry.AddDescriptor(agent.ProviderDescriptor{
		ID:        "codex",
		Label:     "Codex",
		Family:    "codex",
		Transport: "acp",
		Available: true,
	})

	first, changed, from, err := switchThreadBackend(database, registry, 42, "pi")
	if err != nil {
		t.Fatalf("switch to pi: %v", err)
	}
	if !changed {
		t.Fatal("first backend assignment should report changed")
	}
	if from != "" {
		t.Fatalf("first assignment from = %q, want empty", from)
	}
	if first.BackendGeneration != 1 {
		t.Fatalf("first generation = %d, want 1", first.BackendGeneration)
	}

	same, changed, from, err := switchThreadBackend(database, registry, 42, "pi")
	if err != nil {
		t.Fatalf("switch to same backend: %v", err)
	}
	if changed {
		t.Fatal("same backend should not report changed")
	}
	if from != "pi" {
		t.Fatalf("same backend from = %q, want pi", from)
	}
	if same.BackendGeneration != 1 {
		t.Fatalf("same generation = %d, want 1", same.BackendGeneration)
	}

	next, changed, from, err := switchThreadBackend(database, registry, 42, "codex")
	if err != nil {
		t.Fatalf("switch to codex: %v", err)
	}
	if !changed {
		t.Fatal("backend change should report changed")
	}
	if from != "pi" {
		t.Fatalf("backend change from = %q, want pi", from)
	}
	if next.BackendGeneration != 2 {
		t.Fatalf("next generation = %d, want 2", next.BackendGeneration)
	}
}

func TestRecordBackendSwitchStoresSystemInteraction(t *testing.T) {
	database, err := db.Open(t.TempDir() + "/test.db")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()

	if err := recordBackendSwitch(database, nil, 7, "pi", "codex", 2); err != nil {
		t.Fatalf("recordBackendSwitch: %v", err)
	}

	thread, err := database.GetThread(7)
	if err != nil {
		t.Fatalf("GetThread: %v", err)
	}
	if len(thread) != 1 {
		t.Fatalf("thread length = %d, want 1", len(thread))
	}
	var payload db.InteractionData
	if err := json.Unmarshal(thread[0].Data, &payload); err != nil {
		t.Fatalf("unmarshal payload: %v", err)
	}
	if payload.Type != "system" {
		t.Fatalf("payload type = %q, want system", payload.Type)
	}
	if payload.BackendSwitch == nil {
		t.Fatal("payload.BackendSwitch is nil")
	}
	if payload.BackendSwitch.From != "pi" || payload.BackendSwitch.To != "codex" || payload.BackendSwitch.ThreadBackendGeneration != 2 {
		t.Fatalf("unexpected backend switch: %#v", payload.BackendSwitch)
	}
}
