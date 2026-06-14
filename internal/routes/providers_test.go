package routes

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/rcarmo/vibes/internal/agent"
)

type providerRouteStub struct {
	id     string
	status agent.ProviderStatus
	events chan agent.Event
}

func (p *providerRouteStub) ID() string                                  { return p.id }
func (p *providerRouteStub) Initialize(context.Context) error            { return nil }
func (p *providerRouteStub) Prompt(context.Context, string, int64) error { return nil }
func (p *providerRouteStub) Cancel() error                               { return nil }
func (p *providerRouteStub) Events() <-chan agent.Event                  { return p.events }
func (p *providerRouteStub) Status() agent.ProviderStatus                { return p.status }
func (p *providerRouteStub) Shutdown(context.Context) error              { return nil }

func TestGetProvidersIncludesUnavailableDiagnostics(t *testing.T) {
	registry := agent.NewRegistry()
	registry.RegisterWithDescriptor("pi", &providerRouteStub{id: "pi", status: agent.ProviderStatus{State: "idle", Model: "pi-model"}, events: make(chan agent.Event)}, agent.ProviderDescriptor{
		ID:           "pi",
		Label:        "Pi",
		Family:       "pi",
		Transport:    "pi-rpc",
		Available:    true,
		Capabilities: agent.PiCapabilities(),
	})
	registry.AddDescriptor(agent.ProviderDescriptor{
		ID:        "codex",
		Label:     "Codex",
		Family:    "codex",
		Transport: "acp",
		Status:    "missing_binary",
		Error:     "not found",
	})

	req := httptest.NewRequest(http.MethodGet, "/agent/providers", nil)
	rr := httptest.NewRecorder()
	getProviders(registry).ServeHTTP(rr, req)
	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d", rr.Code)
	}
	var body struct {
		Providers []agent.ProviderDescriptor `json:"providers"`
		Active    string                     `json:"active"`
	}
	if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
		t.Fatalf("json: %v", err)
	}
	if len(body.Providers) != 2 {
		t.Fatalf("providers length = %d, want 2", len(body.Providers))
	}
	seen := map[string]agent.ProviderDescriptor{}
	for _, provider := range body.Providers {
		seen[provider.ID] = provider
	}
	if !seen["pi"].Available || !seen["pi"].Ready || seen["pi"].Model != "pi-model" {
		t.Fatalf("unexpected pi descriptor: %#v", seen["pi"])
	}
	if seen["codex"].Available || seen["codex"].Status != "missing_binary" || seen["codex"].Error == "" {
		t.Fatalf("unexpected codex descriptor: %#v", seen["codex"])
	}
}

func TestActivateProviderRejectsUnavailableProvider(t *testing.T) {
	registry := agent.NewRegistry()
	registry.RegisterWithDescriptor("pi", &providerRouteStub{id: "pi", status: agent.ProviderStatus{State: "idle"}, events: make(chan agent.Event)}, agent.ProviderDescriptor{
		ID:        "pi",
		Label:     "Pi",
		Available: true,
	})
	registry.RegisterWithDescriptor("codex", &providerRouteStub{id: "codex", status: agent.ProviderStatus{State: "stopped"}, events: make(chan agent.Event)}, agent.ProviderDescriptor{
		ID:        "codex",
		Label:     "Codex",
		Available: true,
	})
	registry.MarkProviderError("codex", "initialization_failed", "auth required")

	r := chi.NewRouter()
	r.Post("/agent/providers/{id}/activate", activateProvider(registry))
	req := httptest.NewRequest(http.MethodPost, "/agent/providers/codex/activate", nil)
	rr := httptest.NewRecorder()
	r.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", rr.Code)
	}
	if registry.Active() != "pi" {
		t.Fatalf("active = %q, want pi", registry.Active())
	}
}
