package acp

// PromptCapabilities describes prompt content block variants an ACP agent
// advertised during initialize. Text and resource_link are baseline ACP support;
// these fields gate optional variants.
type PromptCapabilities struct {
	Image           bool
	Audio           bool
	EmbeddedContext bool
}

// MCPCapabilities describes optional MCP transports an ACP agent advertised.
// Stdio MCP servers are baseline ACP support and do not need an advertised flag.
type MCPCapabilities struct {
	HTTP bool
	SSE  bool
}

// SessionCapabilities describes optional ACP session methods/features.
type SessionCapabilities struct {
	List                  bool
	Delete                bool
	Resume                bool
	Close                 bool
	AdditionalDirectories bool
}

// Implementation is ACP's client/agent info shape.
type Implementation struct {
	Name    string
	Version string
}

// AuthMethod captures auth method metadata without depending on strict ACP SDK
// unions. Agents in the wild may omit union discriminator fields.
type AuthMethod struct {
	ID          string
	Name        string
	Description string
	Type        string
}

// AgentCapabilities is the negotiated ACP capability snapshot for one provider.
type AgentCapabilities struct {
	Prompt      PromptCapabilities
	MCP         MCPCapabilities
	Session     SessionCapabilities
	AuthMethods []AuthMethod
	AgentInfo   Implementation
}

func parseCapabilities(initResult interface{}) AgentCapabilities {
	var caps AgentCapabilities
	result, _ := initResult.(map[string]interface{})
	if result == nil {
		return caps
	}

	if ai, ok := result["agentInfo"].(map[string]interface{}); ok {
		caps.AgentInfo = Implementation{
			Name:    stringField(ai, "name"),
			Version: stringField(ai, "version"),
		}
	}

	if methods, ok := result["authMethods"].([]interface{}); ok {
		caps.AuthMethods = make([]AuthMethod, 0, len(methods))
		for _, item := range methods {
			m, _ := item.(map[string]interface{})
			if m == nil {
				continue
			}
			caps.AuthMethods = append(caps.AuthMethods, AuthMethod{
				ID:          stringField(m, "id", "methodId"),
				Name:        stringField(m, "name", "title"),
				Description: stringField(m, "description"),
				Type:        stringField(m, "type"),
			})
		}
	}

	agentCaps, _ := result["agentCapabilities"].(map[string]interface{})
	if agentCaps == nil {
		return caps
	}

	if prompt, ok := agentCaps["promptCapabilities"].(map[string]interface{}); ok {
		caps.Prompt.Image = boolField(prompt, "image")
		caps.Prompt.Audio = boolField(prompt, "audio")
		caps.Prompt.EmbeddedContext = boolField(prompt, "embeddedContext", "embedded_context")
	}
	if mcp, ok := agentCaps["mcpCapabilities"].(map[string]interface{}); ok {
		caps.MCP.HTTP = boolField(mcp, "http")
		caps.MCP.SSE = boolField(mcp, "sse")
	}
	if session, ok := agentCaps["sessionCapabilities"].(map[string]interface{}); ok {
		caps.Session.List = objectCapability(session, "list")
		caps.Session.Delete = objectCapability(session, "delete")
		caps.Session.Resume = objectCapability(session, "resume")
		caps.Session.Close = objectCapability(session, "close")
		caps.Session.AdditionalDirectories = objectCapability(session, "additionalDirectories", "additional_directories")
	}
	return caps
}

func stringField(m map[string]interface{}, keys ...string) string {
	for _, key := range keys {
		if value, ok := m[key].(string); ok {
			return value
		}
	}
	return ""
}

func boolField(m map[string]interface{}, keys ...string) bool {
	for _, key := range keys {
		if value, ok := m[key].(bool); ok {
			return value
		}
	}
	return false
}

func objectCapability(m map[string]interface{}, keys ...string) bool {
	for _, key := range keys {
		value, ok := m[key]
		if !ok || value == nil {
			continue
		}
		if enabled, ok := value.(bool); ok {
			return enabled
		}
		if _, ok := value.(map[string]interface{}); ok {
			return true
		}
	}
	return false
}
