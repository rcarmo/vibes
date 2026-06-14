package agent

import (
	"context"
	"testing"
)

// stubProvider is a minimal Provider for testing the registry.
type stubProvider struct {
	id     string
	events chan Event
}

func (s *stubProvider) ID() string                                                   { return s.id }
func (s *stubProvider) Initialize(ctx context.Context) error                         { return nil }
func (s *stubProvider) Prompt(ctx context.Context, msg string, threadID int64) error { return nil }
func (s *stubProvider) Cancel() error                                                { return nil }
func (s *stubProvider) Events() <-chan Event                                         { return s.events }
func (s *stubProvider) Status() ProviderStatus                                       { return ProviderStatus{State: "idle"} }
func (s *stubProvider) Shutdown(ctx context.Context) error                           { return nil }

func newStub(id string) *stubProvider {
	return &stubProvider{id: id, events: make(chan Event)}
}

func TestRegistryRegisterAndGet(t *testing.T) {
	r := NewRegistry()
	r.Register("a", newStub("a"))
	r.Register("b", newStub("b"))

	p, err := r.Get("a")
	if err != nil {
		t.Fatalf("Get(a) failed: %v", err)
	}
	if p.ID() != "a" {
		t.Errorf("got %q, want a", p.ID())
	}
}

func TestRegistryDefaultIsFirst(t *testing.T) {
	r := NewRegistry()
	r.Register("first", newStub("first"))
	r.Register("second", newStub("second"))

	if r.Active() != "first" {
		t.Errorf("Active = %q, want first", r.Active())
	}

	p, err := r.Get("default")
	if err != nil {
		t.Fatalf("Get(default) failed: %v", err)
	}
	if p.ID() != "first" {
		t.Errorf("default returned %q, want first", p.ID())
	}
}

func TestRegistrySetActive(t *testing.T) {
	r := NewRegistry()
	r.Register("a", newStub("a"))
	r.Register("b", newStub("b"))

	if err := r.SetActive("b"); err != nil {
		t.Fatalf("SetActive(b) failed: %v", err)
	}
	if r.Active() != "b" {
		t.Errorf("Active = %q, want b", r.Active())
	}
}

func TestRegistrySetActiveUnknown(t *testing.T) {
	r := NewRegistry()
	r.Register("a", newStub("a"))

	if err := r.SetActive("nonexistent"); err == nil {
		t.Error("SetActive(nonexistent) should have failed")
	}
}

func TestRegistryGetUnknown(t *testing.T) {
	r := NewRegistry()
	if _, err := r.Get("nope"); err == nil {
		t.Error("Get(nope) should have failed")
	}
}

func TestRegistryList(t *testing.T) {
	r := NewRegistry()
	r.Register("a", newStub("a"))
	r.Register("b", newStub("b"))
	r.Register("c", newStub("c"))

	got := r.List()
	if len(got) != 3 {
		t.Errorf("List returned %d items, want 3", len(got))
	}
}

func TestRegistrySetActiveRejectsUnavailableBackend(t *testing.T) {
	r := NewRegistry()
	r.RegisterWithDescriptor("pi", newStub("pi"), ProviderDescriptor{ID: "pi", Label: "Pi", Available: true})
	r.RegisterWithDescriptor("codex", newStub("codex"), ProviderDescriptor{ID: "codex", Label: "Codex", Available: true})
	r.MarkProviderError("codex", "initialization_failed", "auth required")

	if err := r.SetActive("codex"); err == nil {
		t.Fatal("SetActive should reject unavailable backend")
	}
	if r.Active() != "pi" {
		t.Fatalf("Active = %q, want pi", r.Active())
	}
}

func TestRegistryDescriptorsIncludeUnavailableBackends(t *testing.T) {
	r := NewRegistry()
	r.RegisterWithDescriptor("pi", newStub("pi"), ProviderDescriptor{
		ID:           "pi",
		Label:        "Pi",
		Family:       "pi",
		Transport:    "pi-rpc",
		Capabilities: PiCapabilities(),
	})
	r.AddDescriptor(ProviderDescriptor{
		ID:        "codex",
		Label:     "Codex",
		Family:    "codex",
		Transport: "acp",
		Status:    "missing_binary",
		Error:     "not found",
	})

	descriptors := r.Descriptors()
	if len(descriptors) != 2 {
		t.Fatalf("Descriptors length = %d, want 2", len(descriptors))
	}
	seen := map[string]ProviderDescriptor{}
	for _, descriptor := range descriptors {
		seen[descriptor.ID] = descriptor
	}
	if !seen["pi"].Available || !seen["pi"].Ready {
		t.Fatalf("pi descriptor not available/ready: %#v", seen["pi"])
	}
	if seen["codex"].Available {
		t.Fatalf("codex descriptor should not be available: %#v", seen["codex"])
	}
	if seen["codex"].Status != "missing_binary" {
		t.Fatalf("codex status = %q", seen["codex"].Status)
	}
}

func TestRegistryMarkProviderError(t *testing.T) {
	r := NewRegistry()
	r.RegisterWithDescriptor("codex", newStub("codex"), ProviderDescriptor{
		ID:        "codex",
		Label:     "Codex",
		Family:    "codex",
		Transport: "acp",
		Available: true,
	})
	r.MarkProviderError("codex", "initialization_failed", "auth required")
	descriptor, ok := r.Descriptor("codex")
	if !ok {
		t.Fatal("codex descriptor missing")
	}
	if descriptor.Available {
		t.Fatalf("codex should be unavailable after error: %#v", descriptor)
	}
	if descriptor.Status != "initialization_failed" {
		t.Fatalf("status = %q", descriptor.Status)
	}
	if descriptor.Error != "auth required" {
		t.Fatalf("error = %q", descriptor.Error)
	}
}
