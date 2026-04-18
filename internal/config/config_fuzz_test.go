package config

import (
	"strings"
	"testing"
)

// FuzzLoadEnv ensures Load() never panics on arbitrary VIBES_PORT values.
func FuzzLoadEnv(f *testing.F) {
	f.Add("8080")
	f.Add("0")
	f.Add("99999")
	f.Add("not-a-number")
	f.Add("")
	f.Add(strings.Repeat("9", 100))

	f.Fuzz(func(t *testing.T, port string) {
		for _, c := range port {
			if c == 0 || c == '=' {
				t.Skip("invalid env-var value")
			}
		}
		t.Setenv("VIBES_PORT", port)

		// Load should either return a valid config or an error — never panic.
		_, _ = Load()
	})
}

// FuzzLoadHost ensures Load() never panics on arbitrary VIBES_HOST values.
func FuzzLoadHost(f *testing.F) {
	f.Add("0.0.0.0")
	f.Add("127.0.0.1")
	f.Add("::1")
	f.Add("")
	f.Add("invalid host with spaces")
	f.Add(strings.Repeat("a.", 200))

	f.Fuzz(func(t *testing.T, host string) {
		for _, c := range host {
			if c == 0 || c == '=' {
				t.Skip("invalid env-var value")
			}
		}
		t.Setenv("VIBES_HOST", host)
		_, _ = Load()
	})
}

// FuzzLoadDefaultAgent ensures the agent selection logic handles arbitrary input.
func FuzzLoadDefaultAgent(f *testing.F) {
	f.Add("acp")
	f.Add("pi")
	f.Add("ACP")
	f.Add("Pi")
	f.Add("")
	f.Add("unknown")

	f.Fuzz(func(t *testing.T, agent string) {
		// Skip values that cannot be set as environment variables.
		for _, c := range agent {
			if c == 0 || c == '=' {
				t.Skip("invalid env-var value")
			}
		}

		t.Setenv("VIBES_DEFAULT_AGENT", agent)
		cfg, err := Load()
		if err != nil {
			return // valid env-parser error
		}
		// Invariant: if the default agent is "pi", PiEnabled must be true.
		if cfg.DefaultAgent == "pi" && !cfg.PiEnabled {
			t.Errorf("DefaultAgent=pi but PiEnabled=false")
		}
	})
}
