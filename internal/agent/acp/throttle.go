package acp

import (
	"sync"
	"time"
)

// throttler implements a simple token-bucket rate limiter for SSE events. (fixes #12)
type throttler struct {
	mu       sync.Mutex
	rps      int
	tokens   int
	lastFill time.Time
}

func newThrottler(rps int) *throttler {
	if rps <= 0 {
		return nil
	}
	return &throttler{
		rps:      rps,
		tokens:   rps,
		lastFill: time.Now(),
	}
}

// allow returns true if the event should be forwarded.
// Draft and thought events are throttled; tool_call and response events pass through.
func (t *throttler) allow(eventType string) bool {
	if t == nil {
		return true
	}

	// Never throttle control events
	switch eventType {
	case "status", "response", "permission", "error":
		return true
	}

	t.mu.Lock()
	defer t.mu.Unlock()

	// Refill tokens based on elapsed time
	now := time.Now()
	elapsed := now.Sub(t.lastFill)
	newTokens := int(elapsed.Seconds() * float64(t.rps))
	if newTokens > 0 {
		t.tokens += newTokens
		if t.tokens > t.rps {
			t.tokens = t.rps
		}
		t.lastFill = now
	}

	if t.tokens > 0 {
		t.tokens--
		return true
	}
	return false
}
