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
func (s *stubProvider) Cancel() error                                                 { return nil }
func (s *stubProvider) Events() <-chan Event                                          { return s.events }
func (s *stubProvider) Status() ProviderStatus                                        { return ProviderStatus{State: "idle"} }
func (s *stubProvider) Shutdown(ctx context.Context) error                            { return nil }

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
