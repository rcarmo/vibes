package agent

import (
	"context"
	"fmt"
	"sync"
)

// Event represents a streaming event from an agent.
type Event struct {
	Type string      // "draft", "thought", "plan", "status", "response", "permission", "error"
	Data interface{} // Event-specific payload
}

// Provider is the interface all agent backends implement.
type Provider interface {
	// ID returns the provider identifier (e.g., "copilot", "codex", "claude", "pi").
	ID() string

	// Initialize starts the agent subprocess and performs handshake.
	Initialize(ctx context.Context) error

	// Prompt sends a user message and returns when the turn is complete.
	// Streaming events are sent on the Events channel.
	Prompt(ctx context.Context, message string, threadID int64) error

	// Cancel aborts the current prompt.
	Cancel() error

	// Events returns the channel for streaming events.
	Events() <-chan Event

	// Status returns the current agent status.
	Status() ProviderStatus

	// Shutdown stops the agent subprocess.
	Shutdown(ctx context.Context) error
}

// ProviderStatus represents the agent's current state.
type ProviderStatus struct {
	State      string  // "idle", "busy", "error", "stopped"
	Model      string  // current model name
	ContextPct float64 // context window usage (0.0–1.0)
}

// Registry manages multiple agent providers and allows runtime switching.
type Registry struct {
	mu        sync.RWMutex
	providers map[string]Provider
	active    string
}

// NewRegistry creates an empty agent registry.
func NewRegistry() *Registry {
	return &Registry{
		providers: make(map[string]Provider),
	}
}

// Register adds a provider to the registry.
func (r *Registry) Register(id string, p Provider) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.providers[id] = p
	if r.active == "" {
		r.active = id
	}
}

// Get returns a provider by ID. Returns the active provider if id is "default".
func (r *Registry) Get(id string) (Provider, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	if id == "default" {
		id = r.active
	}
	p, ok := r.providers[id]
	if !ok {
		return nil, fmt.Errorf("unknown agent provider: %s", id)
	}
	return p, nil
}

// SetActive changes the active (default) provider.
func (r *Registry) SetActive(id string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, ok := r.providers[id]; !ok {
		return fmt.Errorf("unknown agent provider: %s", id)
	}
	r.active = id
	return nil
}

// List returns all registered provider IDs.
func (r *Registry) List() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()

	ids := make([]string, 0, len(r.providers))
	for id := range r.providers {
		ids = append(ids, id)
	}
	return ids
}

// Active returns the current active provider ID.
func (r *Registry) Active() string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.active
}
