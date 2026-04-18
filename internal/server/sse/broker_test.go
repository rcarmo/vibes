package sse

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestBrokerSubscribeUnsubscribe(t *testing.T) {
	b := NewBroker()
	if b.Count() != 0 {
		t.Errorf("new broker count = %d, want 0", b.Count())
	}

	c := b.Subscribe("client-1")
	if c == nil {
		t.Fatal("Subscribe returned nil")
	}
	if b.Count() != 1 {
		t.Errorf("after subscribe count = %d, want 1", b.Count())
	}

	b.Unsubscribe("client-1")
	if b.Count() != 0 {
		t.Errorf("after unsubscribe count = %d, want 0", b.Count())
	}
}

func TestBrokerBroadcast(t *testing.T) {
	b := NewBroker()
	c1 := b.Subscribe("c1")
	c2 := b.Subscribe("c2")

	event := Event{Type: "test", Data: map[string]string{"hello": "world"}}
	b.Broadcast(event)

	for _, c := range []*Client{c1, c2} {
		select {
		case got := <-c.events:
			if got.Type != "test" {
				t.Errorf("client got Type=%q, want test", got.Type)
			}
		case <-time.After(time.Second):
			t.Error("client did not receive broadcast")
		}
	}
}

func TestBrokerHTTPHandler(t *testing.T) {
	b := NewBroker()
	server := httptest.NewServer(b.Handler())
	defer server.Close()

	// Send an event after the client connects.
	go func() {
		time.Sleep(100 * time.Millisecond)
		b.Broadcast(Event{Type: "ping"})
	}()

	req, _ := http.NewRequest("GET", server.URL, nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("GET failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.Header.Get("Content-Type") != "text/event-stream" {
		t.Errorf("Content-Type = %q, want text/event-stream", resp.Header.Get("Content-Type"))
	}

	// Read a small chunk to verify SSE format.
	buf := make([]byte, 256)
	resp.Body.Read(buf)
	body := string(buf)
	if !strings.Contains(body, "event: connected") {
		t.Errorf("response missing connected event:\n%s", body)
	}
}

func TestBrokerDropsWhenBufferFull(t *testing.T) {
	b := NewBroker()
	c := b.Subscribe("slow")

	// Fill the buffer beyond capacity (chan has cap 64).
	for i := 0; i < 100; i++ {
		b.Broadcast(Event{Type: "spam", Data: i})
	}

	// Drain what we can.
	count := 0
	for {
		select {
		case <-c.events:
			count++
		default:
			goto done
		}
	}
done:
	if count == 0 {
		t.Error("no events received")
	}
	if count > 64 {
		t.Errorf("received %d events, expected <= 64 (channel capacity)", count)
	}
}
