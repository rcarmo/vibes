package acp

import "testing"

func TestParseCapabilitiesFullInitializeResponse(t *testing.T) {
	caps := parseCapabilities(map[string]interface{}{
		"agentInfo": map[string]interface{}{"name": "Test Agent", "version": "1.2.3"},
		"authMethods": []interface{}{
			map[string]interface{}{"id": "oauth", "name": "OAuth", "description": "Browser login", "type": "oauth"},
		},
		"agentCapabilities": map[string]interface{}{
			"promptCapabilities": map[string]interface{}{
				"image":           true,
				"audio":           true,
				"embeddedContext": true,
			},
			"mcpCapabilities": map[string]interface{}{"http": true, "sse": true},
			"sessionCapabilities": map[string]interface{}{
				"list":                  map[string]interface{}{},
				"delete":                map[string]interface{}{},
				"resume":                map[string]interface{}{},
				"close":                 map[string]interface{}{},
				"additionalDirectories": map[string]interface{}{},
			},
		},
	})

	if caps.AgentInfo.Name != "Test Agent" || caps.AgentInfo.Version != "1.2.3" {
		t.Fatalf("agent info = %#v", caps.AgentInfo)
	}
	if len(caps.AuthMethods) != 1 || caps.AuthMethods[0].ID != "oauth" {
		t.Fatalf("auth methods = %#v", caps.AuthMethods)
	}
	if !caps.Prompt.Image || !caps.Prompt.Audio || !caps.Prompt.EmbeddedContext {
		t.Fatalf("prompt caps = %#v", caps.Prompt)
	}
	if !caps.MCP.HTTP || !caps.MCP.SSE {
		t.Fatalf("mcp caps = %#v", caps.MCP)
	}
	if !caps.Session.List || !caps.Session.Delete || !caps.Session.Resume || !caps.Session.Close || !caps.Session.AdditionalDirectories {
		t.Fatalf("session caps = %#v", caps.Session)
	}
}

func TestParseCapabilitiesMinimalInitializeResponse(t *testing.T) {
	caps := parseCapabilities(map[string]interface{}{"protocolVersion": 1.0})
	if caps.Prompt.Image || caps.Prompt.Audio || caps.Prompt.EmbeddedContext || caps.MCP.HTTP || caps.MCP.SSE {
		t.Fatalf("unexpected enabled caps = %#v", caps)
	}
}

func TestProviderCapabilitiesReflectNegotiatedACP(t *testing.T) {
	p := New(Config{ID: "codex"})
	p.setCapabilities(AgentCapabilities{
		Prompt:  PromptCapabilities{Image: true, EmbeddedContext: true},
		MCP:     MCPCapabilities{HTTP: true},
		Session: SessionCapabilities{List: true, Resume: true},
	})

	caps := p.Capabilities()
	if !caps.MCPServers || !caps.MCPHTTP || caps.MCPSSE {
		t.Fatalf("mcp provider caps = %#v", caps)
	}
	if !caps.PromptImages || !caps.EmbeddedContext || caps.PromptAudio {
		t.Fatalf("prompt provider caps = %#v", caps)
	}
	if !caps.SessionList || !caps.SessionResume || caps.SessionClose {
		t.Fatalf("session provider caps = %#v", caps)
	}
}
