package sse

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"sync"
)

// Event is a server-sent event.
type Event struct {
	Type string      `json:"type"`
	Data interface{} `json:"data,omitempty"`
}

// Client represents a connected SSE client.
type Client struct {
	id     string
	events chan Event
	done   chan struct{}
}

// Events returns the client's event stream for tests and internal integrations
// that need to observe broker fanout without serving HTTP.
func (c *Client) Events() <-chan Event { return c.events }

// Broker manages SSE client connections and event fanout.
type Broker struct {
	mu          sync.RWMutex
	clients     map[string]*Client
	onEmpty     func() // called when last client disconnects (fixes #9)
	onReconnect func() // called when first client connects after empty
}

// NewBroker creates a new SSE broker.
func NewBroker() *Broker {
	return &Broker{
		clients: make(map[string]*Client),
	}
}

// OnEmpty sets a callback for when all clients disconnect.
func (b *Broker) OnEmpty(fn func()) { b.onEmpty = fn }

// OnReconnect sets a callback for when first client connects after being empty.
func (b *Broker) OnReconnect(fn func()) { b.onReconnect = fn }

// Subscribe adds a new client and returns it.
func (b *Broker) Subscribe(id string) *Client {
	wasEmpty := b.Count() == 0

	client := &Client{
		id:     id,
		events: make(chan Event, 64),
		done:   make(chan struct{}),
	}

	b.mu.Lock()
	b.clients[id] = client
	b.mu.Unlock()

	slog.Debug("SSE client connected", "id", id, "total", b.Count())

	if wasEmpty && b.onReconnect != nil {
		go b.onReconnect()
	}

	return client
}

// Unsubscribe removes a client.
func (b *Broker) Unsubscribe(id string) {
	b.mu.Lock()
	if client, ok := b.clients[id]; ok {
		close(client.done)
		delete(b.clients, id)
	}
	b.mu.Unlock()

	slog.Debug("SSE client disconnected", "id", id, "total", b.Count())

	if b.Count() == 0 && b.onEmpty != nil {
		go b.onEmpty()
	}
}

// Broadcast sends an event to all connected clients.
func (b *Broker) Broadcast(event Event) {
	b.mu.RLock()
	defer b.mu.RUnlock()

	for _, client := range b.clients {
		select {
		case client.events <- event:
		default:
			slog.Warn("SSE client buffer full, dropping event", "id", client.id)
		}
	}
}

// Count returns the number of connected clients.
func (b *Broker) Count() int {
	b.mu.RLock()
	defer b.mu.RUnlock()
	return len(b.clients)
}

// Handler returns an http.HandlerFunc that serves the SSE stream.
func (b *Broker) Handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "streaming not supported", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")
		if allowOrigin := os.Getenv("VIBES_CORS_ALLOW_ORIGIN"); allowOrigin != "" {
			origin := r.Header.Get("Origin")
			if allowOrigin == "*" || origin == allowOrigin {
				if origin != "" {
					w.Header().Set("Access-Control-Allow-Origin", origin)
				} else {
					w.Header().Set("Access-Control-Allow-Origin", allowOrigin)
				}
				w.Header().Set("Vary", "Origin")
			}
		}

		clientID := r.RemoteAddr
		if id := r.URL.Query().Get("client_id"); id != "" {
			clientID = id
		}

		client := b.Subscribe(clientID)
		defer b.Unsubscribe(clientID)

		// Send connected event
		sendSSE(w, flusher, Event{Type: "connected", Data: map[string]string{"client_id": clientID}})

		for {
			select {
			case event := <-client.events:
				sendSSE(w, flusher, event)
			case <-client.done:
				return
			case <-r.Context().Done():
				return
			}
		}
	}
}

func sendSSE(w http.ResponseWriter, flusher http.Flusher, event Event) {
	data, err := json.Marshal(event.Data)
	if err != nil {
		slog.Warn("SSE marshal error", "error", err)
		return
	}
	fmt.Fprintf(w, "event: %s\ndata: %s\n\n", event.Type, data)
	flusher.Flush()
}
