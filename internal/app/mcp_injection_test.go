package app

import (
	"testing"

	"github.com/rcarmo/vibes/internal/agent/acp"
	"github.com/rcarmo/vibes/internal/config"
)

func TestAppendVibesMCPServerDisabledByDefault(t *testing.T) {
	servers := []acp.MCPServer{{Name: "existing", Type: "stdio", Command: "existing-mcp"}}
	out := appendVibesMCPServer(servers, &config.Config{})
	if len(out) != 1 || out[0].Name != "existing" {
		t.Fatalf("servers = %#v", out)
	}
}

func TestAppendVibesMCPServerRequiresAutoInject(t *testing.T) {
	out := appendVibesMCPServer(nil, &config.Config{VibesMCPEnabled: true})
	if len(out) != 0 {
		t.Fatalf("servers = %#v", out)
	}
}

func TestAppendVibesMCPServerUsesConfiguredCommand(t *testing.T) {
	out := appendVibesMCPServer(nil, &config.Config{
		VibesMCPEnabled:       true,
		VibesMCPAutoInjectACP: true,
		VibesMCPCommand:       "/usr/local/bin/vibes mcp --stdio",
	})
	if len(out) != 1 {
		t.Fatalf("servers = %#v", out)
	}
	server := out[0]
	if server.Name != "vibes" || server.Type != "stdio" || server.Command != "/usr/local/bin/vibes" {
		t.Fatalf("server = %#v", server)
	}
	if len(server.Args) != 2 || server.Args[0] != "mcp" || server.Args[1] != "--stdio" {
		t.Fatalf("args = %#v", server.Args)
	}
}
