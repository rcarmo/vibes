package acp

import (
	"encoding/json"
	"fmt"
	"strings"
)

// MCPServer is a permissive representation of ACP's McpServer union. Type is
// optional for stdio because ACP's schema treats stdio as the baseline variant.
type MCPServer struct {
	Type    string            `json:"type,omitempty"`
	Name    string            `json:"name"`
	Command string            `json:"command,omitempty"`
	Args    []string          `json:"args,omitempty"`
	Env     map[string]string `json:"env,omitempty"`
	URL     string            `json:"url,omitempty"`
	Headers map[string]string `json:"headers,omitempty"`
}

// ParseMCPServersJSON parses VIBES_ACP_MCP_SERVERS_JSON. Empty input means no
// configured servers. Secrets should be referenced through inherited agent env
// or explicit env names rather than committed into config files.
func ParseMCPServersJSON(raw string) ([]MCPServer, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	var servers []MCPServer
	if err := json.Unmarshal([]byte(raw), &servers); err != nil {
		return nil, fmt.Errorf("parse ACP MCP servers JSON: %w", err)
	}
	for i := range servers {
		servers[i].Type = normalizeMCPType(servers[i].Type)
		if err := servers[i].Validate(); err != nil {
			return nil, fmt.Errorf("mcpServers[%d]: %w", i, err)
		}
	}
	return servers, nil
}

func normalizeMCPType(t string) string {
	t = strings.ToLower(strings.TrimSpace(t))
	if t == "" {
		return "stdio"
	}
	return t
}

func (s MCPServer) Validate() error {
	if strings.TrimSpace(s.Name) == "" {
		return fmt.Errorf("name is required")
	}
	switch normalizeMCPType(s.Type) {
	case "stdio":
		if strings.TrimSpace(s.Command) == "" {
			return fmt.Errorf("command is required for stdio MCP server")
		}
	case "http", "sse":
		if strings.TrimSpace(s.URL) == "" {
			return fmt.Errorf("url is required for %s MCP server", normalizeMCPType(s.Type))
		}
	default:
		return fmt.Errorf("unsupported MCP server type %q", s.Type)
	}
	return nil
}

func filterMCPServers(servers []MCPServer, caps AgentCapabilities) []map[string]interface{} {
	out := make([]map[string]interface{}, 0, len(servers))
	for _, server := range servers {
		t := normalizeMCPType(server.Type)
		if t == "http" && !caps.MCP.HTTP {
			continue
		}
		if t == "sse" && !caps.MCP.SSE {
			continue
		}
		out = append(out, server.toACP())
	}
	return out
}

func (s MCPServer) toACP() map[string]interface{} {
	t := normalizeMCPType(s.Type)
	m := map[string]interface{}{
		"name": strings.TrimSpace(s.Name),
	}
	if t != "stdio" {
		m["type"] = t
	}
	switch t {
	case "stdio":
		m["command"] = s.Command
		m["args"] = stringSliceOrEmpty(s.Args)
		m["env"] = envArray(s.Env)
	case "http", "sse":
		m["url"] = s.URL
		m["headers"] = headerArray(s.Headers)
	}
	return m
}

func stringSliceOrEmpty(values []string) []string {
	if values == nil {
		return []string{}
	}
	return values
}

func envArray(env map[string]string) []map[string]string {
	items := make([]map[string]string, 0, len(env))
	for name, value := range env {
		items = append(items, map[string]string{"name": name, "value": value})
	}
	return items
}

func headerArray(headers map[string]string) []map[string]string {
	items := make([]map[string]string, 0, len(headers))
	for name, value := range headers {
		items = append(items, map[string]string{"name": name, "value": value})
	}
	return items
}
