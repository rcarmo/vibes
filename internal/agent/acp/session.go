package acp

func (p *Provider) sessionNewParams(cwd string, caps AgentCapabilities) map[string]interface{} {
	return map[string]interface{}{
		"cwd":        cwd,
		"mcpServers": filterMCPServers(p.cfg.MCPServers, caps),
	}
}
