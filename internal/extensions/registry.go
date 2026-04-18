package extensions

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
)

// Route defines an HTTP route contributed by an extension.
type Route struct {
	Method  string
	Pattern string
	Handler http.HandlerFunc
}

// PanelDef describes a UI panel registered by an extension.
type PanelDef struct {
	ID       string `json:"id"`
	Title    string `json:"title"`
	Position string `json:"position"` // "sidebar", "main", "overlay", "toolbar"
	Icon     string `json:"icon"`     // Font Awesome class or SVG path
	Default  bool   `json:"default"`  // visible by default
}

// Manifest describes frontend assets and UI panels for an extension.
type Manifest struct {
	Panels []PanelDef `json:"panels"`
	CSS    []string   `json:"css"` // relative paths under /ext/{id}/
	JS     []string   `json:"js"`  // relative paths under /ext/{id}/
}

// Extension is the interface all extensions implement.
type Extension interface {
	// Metadata
	ID() string
	Name() string
	Version() string

	// Lifecycle
	Init(ctx context.Context) error
	Shutdown(ctx context.Context) error

	// HTTP routes (optional — return nil for no routes)
	Routes() []Route

	// SSE event types this extension emits (optional)
	EventTypes() []string

	// Static assets directory (optional — served under /ext/{id}/)
	StaticDir() string

	// Frontend manifest (optional — for UI panel registration)
	Manifest() *Manifest
}

// Registry manages extension discovery, lifecycle, and route collection.
type Registry struct {
	mu         sync.RWMutex
	extensions map[string]Extension
	order      []string // registration order
}

// NewRegistry creates an empty extension registry.
func NewRegistry() *Registry {
	return &Registry{
		extensions: make(map[string]Extension),
	}
}

// Register adds an extension to the registry.
func (r *Registry) Register(ext Extension) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	id := ext.ID()
	if _, exists := r.extensions[id]; exists {
		return fmt.Errorf("extension %q already registered", id)
	}

	r.extensions[id] = ext
	r.order = append(r.order, id)
	slog.Info("registered extension", "id", id, "name", ext.Name(), "version", ext.Version())
	return nil
}

// InitAll initializes all registered extensions in registration order.
func (r *Registry) InitAll(ctx context.Context) error {
	r.mu.RLock()
	defer r.mu.RUnlock()

	for _, id := range r.order {
		ext := r.extensions[id]
		slog.Debug("initializing extension", "id", id)
		if err := ext.Init(ctx); err != nil {
			return fmt.Errorf("init extension %s: %w", id, err)
		}
	}
	return nil
}

// ShutdownAll shuts down all extensions in reverse order.
func (r *Registry) ShutdownAll(ctx context.Context) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	for i := len(r.order) - 1; i >= 0; i-- {
		ext := r.extensions[r.order[i]]
		if err := ext.Shutdown(ctx); err != nil {
			slog.Warn("extension shutdown error", "id", ext.ID(), "error", err)
		}
	}
}

// AllRoutes collects HTTP routes from all extensions.
func (r *Registry) AllRoutes() []Route {
	r.mu.RLock()
	defer r.mu.RUnlock()

	var routes []Route
	for _, id := range r.order {
		ext := r.extensions[id]
		if extRoutes := ext.Routes(); extRoutes != nil {
			routes = append(routes, extRoutes...)
		}
	}
	return routes
}

// AllManifests returns frontend manifests for all extensions that have one.
func (r *Registry) AllManifests() map[string]*Manifest {
	r.mu.RLock()
	defer r.mu.RUnlock()

	manifests := make(map[string]*Manifest)
	for _, id := range r.order {
		ext := r.extensions[id]
		if m := ext.Manifest(); m != nil {
			manifests[id] = m
		}
	}
	return manifests
}

// Get returns an extension by ID.
func (r *Registry) Get(id string) (Extension, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	ext, ok := r.extensions[id]
	return ext, ok
}

// List returns all extension IDs in registration order.
func (r *Registry) List() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]string, len(r.order))
	copy(out, r.order)
	return out
}
