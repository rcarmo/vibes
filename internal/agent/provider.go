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

// ProviderCapabilities describes optional backend features. The frontend uses
// this to hide unsupported controls rather than assuming feature parity.
type ProviderCapabilities struct {
	StreamingDrafts    bool     `json:"streaming_drafts"`
	StreamingThoughts  bool     `json:"streaming_thoughts"`
	ToolEvents         bool     `json:"tool_events"`
	PermissionRequests bool     `json:"permission_requests"`
	ModelList          bool     `json:"model_list"`
	ModelSwitch        bool     `json:"model_switch"`
	ThinkingLevels     []string `json:"thinking_levels,omitempty"`
	SessionReset       bool     `json:"session_reset"`
	SessionCompact     bool     `json:"session_compact"`
	SessionRename      bool     `json:"session_rename"`
	SessionStats       bool     `json:"session_stats"`
	MessageHistory     bool     `json:"message_history"`
	CommandsList       bool     `json:"commands_list"`
	Steering           bool     `json:"steering"`
	FollowUpQueue      bool     `json:"follow_up_queue"`
	WorkingDirectory   bool     `json:"working_directory"`
	ToolsMode          []string `json:"tools_mode,omitempty"`
}

// ProviderDescriptor is the public identity, transport, availability and
// capability record for a backend.
type ProviderDescriptor struct {
	ID           string               `json:"id"`
	Label        string               `json:"label"`
	Family       string               `json:"family"`
	Transport    string               `json:"transport"`
	Command      string               `json:"command,omitempty"`
	Configured   bool                 `json:"configured"`
	Detected     bool                 `json:"detected"`
	Available    bool                 `json:"available"`
	Ready        bool                 `json:"ready"`
	Active       bool                 `json:"active"`
	Status       string               `json:"status"`
	Error        string               `json:"error,omitempty"`
	Model        string               `json:"model,omitempty"`
	Capabilities ProviderCapabilities `json:"capabilities"`
}

// Registry manages multiple agent providers and allows runtime switching.
type Registry struct {
	mu          sync.RWMutex
	providers   map[string]Provider
	descriptors map[string]ProviderDescriptor
	active      string
}

// NewRegistry creates an empty agent registry.
func NewRegistry() *Registry {
	return &Registry{
		providers:   make(map[string]Provider),
		descriptors: make(map[string]ProviderDescriptor),
	}
}

// Register adds a provider to the registry.
func (r *Registry) Register(id string, p Provider) {
	r.RegisterWithDescriptor(id, p, ProviderDescriptor{ID: id, Label: id, Family: id, Configured: true, Detected: true, Available: true})
}

// RegisterWithDescriptor adds a provider and its public descriptor.
func (r *Registry) RegisterWithDescriptor(id string, p Provider, descriptor ProviderDescriptor) {
	r.mu.Lock()
	defer r.mu.Unlock()
	descriptor.ID = id
	descriptor.Available = true
	descriptor.Detected = true
	if descriptor.Label == "" {
		descriptor.Label = id
	}
	r.providers[id] = p
	r.descriptors[id] = descriptor
	if r.active == "" {
		r.active = id
	}
}

// AddDescriptor adds an unavailable/configured backend descriptor.
func (r *Registry) AddDescriptor(descriptor ProviderDescriptor) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if descriptor.ID == "" {
		return
	}
	if descriptor.Label == "" {
		descriptor.Label = descriptor.ID
	}
	r.descriptors[descriptor.ID] = descriptor
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

// Descriptors returns all configured/detected backend descriptors, including
// unavailable backends.
func (r *Registry) Descriptors() []ProviderDescriptor {
	r.mu.RLock()
	defer r.mu.RUnlock()

	items := make([]ProviderDescriptor, 0, len(r.descriptors))
	for id, descriptor := range r.descriptors {
		descriptor.Active = id == r.active
		if p, ok := r.providers[id]; ok && p != nil {
			status := p.Status()
			descriptor.Model = status.Model
			descriptor.Ready = status.State == "idle" || status.State == "busy"
			descriptor.Status = status.State
			descriptor.Available = true
		} else if descriptor.Status == "" {
			descriptor.Status = "unavailable"
		}
		items = append(items, descriptor)
	}
	return items
}

// Descriptor returns a single backend descriptor.
func (r *Registry) Descriptor(id string) (ProviderDescriptor, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	descriptor, ok := r.descriptors[id]
	if !ok {
		return ProviderDescriptor{}, false
	}
	descriptor.Active = id == r.active
	if p, ok := r.providers[id]; ok && p != nil {
		status := p.Status()
		descriptor.Model = status.Model
		descriptor.Ready = status.State == "idle" || status.State == "busy"
		descriptor.Status = status.State
		descriptor.Available = true
	} else if descriptor.Status == "" {
		descriptor.Status = "unavailable"
	}
	return descriptor, true
}

// Active returns the current active provider ID.
func (r *Registry) Active() string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.active
}
