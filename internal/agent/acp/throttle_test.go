package acp

import (
	"testing"
	"time"
)

func TestThrottlerNil(t *testing.T) {
	var th *throttler
	if !th.allow("draft") {
		t.Error("nil throttler should always allow")
	}
}

func TestThrottlerDisabled(t *testing.T) {
	th := newThrottler(0)
	if th != nil {
		t.Error("rps=0 should return nil throttler")
	}
}

func TestThrottlerControlEventsPassThrough(t *testing.T) {
	th := newThrottler(1) // very low rate
	for _, et := range []string{"status", "response", "permission", "error"} {
		if !th.allow(et) {
			t.Errorf("control event %q was throttled", et)
		}
	}
}

func TestThrottlerLimits(t *testing.T) {
	th := newThrottler(2) // 2 events per second

	// Should allow first 2
	if !th.allow("draft") {
		t.Error("first event should be allowed")
	}
	if !th.allow("draft") {
		t.Error("second event should be allowed")
	}

	// Third should be throttled (no time to refill)
	if th.allow("draft") {
		t.Error("third event should be throttled")
	}

	// After waiting, should allow again
	time.Sleep(600 * time.Millisecond)
	if !th.allow("draft") {
		t.Error("after wait, should allow again")
	}
}
