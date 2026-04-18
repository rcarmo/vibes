package config

import (
	"os"
	"testing"
)

func TestLoadDefaults(t *testing.T) {
	// Clear any VIBES_* env so we get pristine defaults.
	for _, e := range os.Environ() {
		if len(e) > 6 && e[:6] == "VIBES_" {
			key := e[:len("VIBES_")+findEqual(e[6:])]
			os.Unsetenv(key[:findEqual(key)])
		}
	}

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load failed: %v", err)
	}

	if cfg.Host != "0.0.0.0" {
		t.Errorf("Host = %q, want 0.0.0.0", cfg.Host)
	}
	if cfg.Port != 8080 {
		t.Errorf("Port = %d, want 8080", cfg.Port)
	}
	if cfg.DefaultAgent != "acp" {
		t.Errorf("DefaultAgent = %q, want acp", cfg.DefaultAgent)
	}
	if cfg.PiEnabled {
		t.Error("PiEnabled should be false by default")
	}
}

func TestLoadFromEnv(t *testing.T) {
	t.Setenv("VIBES_HOST", "127.0.0.1")
	t.Setenv("VIBES_PORT", "3000")
	t.Setenv("VIBES_DEFAULT_AGENT", "pi")
	t.Setenv("VIBES_DEBUG", "true")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load failed: %v", err)
	}

	if cfg.Host != "127.0.0.1" {
		t.Errorf("Host = %q, want 127.0.0.1", cfg.Host)
	}
	if cfg.Port != 3000 {
		t.Errorf("Port = %d, want 3000", cfg.Port)
	}
	if cfg.DefaultAgent != "pi" {
		t.Errorf("DefaultAgent = %q, want pi", cfg.DefaultAgent)
	}
	if !cfg.Debug {
		t.Error("Debug should be true")
	}
	// Auto-enabled when default agent is pi
	if !cfg.PiEnabled {
		t.Error("PiEnabled should auto-enable when DEFAULT_AGENT=pi")
	}
}

func TestACPAgentDefault(t *testing.T) {
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load failed: %v", err)
	}
	if cfg.ACPAgent == "" {
		t.Error("ACPAgent should have a non-empty default")
	}
}

// findEqual returns the index of the first '=' in s, or len(s).
func findEqual(s string) int {
	for i, c := range s {
		if c == '=' {
			return i
		}
	}
	return len(s)
}
