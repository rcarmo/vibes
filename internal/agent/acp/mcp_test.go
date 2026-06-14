package acp

import "testing"

func TestParseMCPServersJSONValidatesShape(t *testing.T) {
	servers, err := ParseMCPServersJSON(`[
		{"name":"stdio-tools","command":"tools-mcp","args":["--safe"],"env":{"SAFE":"1"}},
		{"type":"http","name":"http-tools","url":"https://example.test/mcp","headers":{"Authorization":"Bearer ${TOKEN}"}}
	]`)
	if err != nil {
		t.Fatalf("ParseMCPServersJSON: %v", err)
	}
	if len(servers) != 2 {
		t.Fatalf("servers len = %d, want 2", len(servers))
	}
	if servers[0].Type != "stdio" || servers[0].Command != "tools-mcp" {
		t.Fatalf("stdio server = %#v", servers[0])
	}
	if servers[1].Type != "http" || servers[1].Headers["Authorization"] == "" {
		t.Fatalf("http server = %#v", servers[1])
	}
}

func TestParseMCPServersJSONRejectsInvalidServers(t *testing.T) {
	cases := []string{
		`[{"name":"missing-command"}]`,
		`[{"type":"http","name":"missing-url"}]`,
		`[{"type":"bogus","name":"bad"}]`,
	}
	for _, tc := range cases {
		if _, err := ParseMCPServersJSON(tc); err == nil {
			t.Fatalf("ParseMCPServersJSON(%s) succeeded, want error", tc)
		}
	}
}

func TestFilterMCPServersByNegotiatedCapabilities(t *testing.T) {
	servers := []MCPServer{
		{Name: "stdio", Type: "stdio", Command: "stdio-mcp"},
		{Name: "http", Type: "http", URL: "https://example.test/mcp"},
		{Name: "sse", Type: "sse", URL: "https://example.test/sse"},
	}

	filtered := filterMCPServers(servers, AgentCapabilities{MCP: MCPCapabilities{HTTP: true}})
	if len(filtered) != 2 {
		t.Fatalf("filtered len = %d, want stdio+http", len(filtered))
	}
	if filtered[0]["name"] != "stdio" || filtered[1]["name"] != "http" {
		t.Fatalf("filtered = %#v", filtered)
	}
	if _, ok := filtered[0]["type"]; ok {
		t.Fatalf("stdio MCP server should omit type for ACP schema compatibility: %#v", filtered[0])
	}
}

func TestSessionNewParamsIncludesFilteredMCPServers(t *testing.T) {
	p := New(Config{ID: "copilot", MCPServers: []MCPServer{
		{Name: "stdio", Type: "stdio", Command: "stdio-mcp", Args: []string{"--root", "/tmp"}},
		{Name: "sse", Type: "sse", URL: "https://example.test/sse"},
	}})

	params := p.sessionNewParams("/workspace", AgentCapabilities{})
	if params["cwd"] != "/workspace" {
		t.Fatalf("cwd = %#v", params["cwd"])
	}
	servers, ok := params["mcpServers"].([]map[string]interface{})
	if !ok {
		t.Fatalf("mcpServers type = %T", params["mcpServers"])
	}
	if len(servers) != 1 || servers[0]["name"] != "stdio" {
		t.Fatalf("mcpServers = %#v", servers)
	}
}
