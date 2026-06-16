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
	if !cfg.PiEnabled {
		t.Error("PiEnabled should be true by default for hybrid discovery")
	}
	if cfg.ACPFSWriteTextEnabled {
		t.Error("ACPFSWriteTextEnabled should be false by default")
	}
	if cfg.ACPFSWriteAllowOverwrite {
		t.Error("ACPFSWriteAllowOverwrite should be false by default")
	}
	if cfg.ACPFSWriteTextMaxBytes != 262144 {
		t.Errorf("ACPFSWriteTextMaxBytes = %d", cfg.ACPFSWriteTextMaxBytes)
	}
	if cfg.VibesMCPEnabled || cfg.VibesMCPAutoInjectACP {
		t.Error("bundled Vibes MCP adapter should be disabled by default")
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
	// Pi is enabled by default for hybrid discovery and remains enabled when default agent is pi.
	if !cfg.PiEnabled {
		t.Error("PiEnabled should be enabled when DEFAULT_AGENT=pi")
	}
}

func TestPiCanBeDisabled(t *testing.T) {
	t.Setenv("VIBES_PI_ENABLED", "false")
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load failed: %v", err)
	}
	if cfg.PiEnabled {
		t.Error("PiEnabled should be false when explicitly disabled")
	}
}

func TestBackendDefaults(t *testing.T) {
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load failed: %v", err)
	}
	if cfg.CopilotAgent == "" {
		t.Error("CopilotAgent should have a non-empty default")
	}
	if cfg.CodexAgent == "" {
		t.Error("CodexAgent should have a non-empty default")
	}
	if !cfg.CopilotEnabled {
		t.Error("CopilotEnabled should default to true")
	}
	if !cfg.CodexEnabled {
		t.Error("CodexEnabled should default to true")
	}
}

func TestBackendEnvOverrides(t *testing.T) {
	t.Setenv("VIBES_COPILOT_AGENT", "custom-copilot --acp")
	t.Setenv("VIBES_COPILOT_ENABLED", "false")
	t.Setenv("VIBES_CODEX_AGENT", "custom-codex")
	t.Setenv("VIBES_CODEX_ENABLED", "false")
	t.Setenv("VIBES_ACP_MCP_SERVERS_JSON", `[{"name":"tools","command":"tools-mcp"}]`)
	t.Setenv("VIBES_ACP_FS_READ_TEXT_ENABLED", "true")
	t.Setenv("VIBES_ACP_FS_READ_TEXT_MAX_BYTES", "1024")
	t.Setenv("VIBES_ACP_FS_WRITE_TEXT_ENABLED", "true")
	t.Setenv("VIBES_ACP_FS_WRITE_ROOT", "/tmp/vibes-write")
	t.Setenv("VIBES_ACP_FS_WRITE_TEXT_MAX_BYTES", "2048")
	t.Setenv("VIBES_ACP_FS_WRITE_ALLOW_OVERWRITE", "true")
	t.Setenv("VIBES_MCP_ENABLED", "true")
	t.Setenv("VIBES_MCP_AUTO_INJECT_ACP", "true")
	t.Setenv("VIBES_MCP_COMMAND", "vibes mcp --stdio")
	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load failed: %v", err)
	}
	if cfg.CopilotAgent != "custom-copilot --acp" {
		t.Errorf("CopilotAgent = %q", cfg.CopilotAgent)
	}
	if cfg.CopilotEnabled {
		t.Error("CopilotEnabled should be false")
	}
	if cfg.CodexAgent != "custom-codex" {
		t.Errorf("CodexAgent = %q", cfg.CodexAgent)
	}
	if cfg.CodexEnabled {
		t.Error("CodexEnabled should be false")
	}
	if cfg.ACPMCPServersJSON == "" {
		t.Error("ACPMCPServersJSON should load from env")
	}
	if !cfg.ACPFSReadTextEnabled {
		t.Error("ACPFSReadTextEnabled should load from env")
	}
	if cfg.ACPFSReadTextMaxBytes != 1024 {
		t.Errorf("ACPFSReadTextMaxBytes = %d", cfg.ACPFSReadTextMaxBytes)
	}
	if !cfg.ACPFSWriteTextEnabled {
		t.Error("ACPFSWriteTextEnabled should load from env")
	}
	if cfg.ACPFSWriteRoot != "/tmp/vibes-write" {
		t.Errorf("ACPFSWriteRoot = %q", cfg.ACPFSWriteRoot)
	}
	if cfg.ACPFSWriteTextMaxBytes != 2048 {
		t.Errorf("ACPFSWriteTextMaxBytes = %d", cfg.ACPFSWriteTextMaxBytes)
	}
	if !cfg.ACPFSWriteAllowOverwrite {
		t.Error("ACPFSWriteAllowOverwrite should load from env")
	}
	if !cfg.VibesMCPEnabled || !cfg.VibesMCPAutoInjectACP {
		t.Error("Vibes MCP flags should load from env")
	}
	if cfg.VibesMCPCommand != "vibes mcp --stdio" {
		t.Errorf("VibesMCPCommand = %q", cfg.VibesMCPCommand)
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
