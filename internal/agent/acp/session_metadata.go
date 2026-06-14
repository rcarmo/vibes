package acp

import "github.com/rcarmo/vibes/internal/agent"

const maxSessionMetadataItems = 32

func (p *Provider) setSessionMetadata(metadata agent.ProviderSessionMetadata) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.sessionMetadata = metadata
}

// SessionMetadata returns display-only ACP session/new metadata.
func (p *Provider) SessionMetadata() agent.ProviderSessionMetadata {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return cloneSessionMetadata(p.sessionMetadata)
}

func parseSessionMetadata(result map[string]interface{}) agent.ProviderSessionMetadata {
	return agent.ProviderSessionMetadata{
		Modes:         parseStringList(result["modes"], maxSessionMetadataItems),
		ConfigOptions: parseConfigOptions(result["configOptions"], maxSessionMetadataItems),
	}
}

func parseStringList(value interface{}, max int) []string {
	items, ok := value.([]interface{})
	if !ok || max <= 0 {
		return nil
	}
	out := make([]string, 0, min(len(items), max))
	for _, item := range items {
		if len(out) >= max {
			break
		}
		if s, ok := item.(string); ok && s != "" {
			out = append(out, s)
		}
	}
	return out
}

func parseConfigOptions(value interface{}, max int) []map[string]interface{} {
	items, ok := value.([]interface{})
	if !ok || max <= 0 {
		return nil
	}
	out := make([]map[string]interface{}, 0, min(len(items), max))
	for _, item := range items {
		if len(out) >= max {
			break
		}
		m, ok := item.(map[string]interface{})
		if !ok {
			continue
		}
		clean := map[string]interface{}{}
		for _, key := range []string{"id", "name", "description", "type", "default", "values"} {
			if v, ok := m[key]; ok {
				clean[key] = v
			}
		}
		if len(clean) > 0 {
			out = append(out, clean)
		}
	}
	return out
}

func cloneSessionMetadata(in agent.ProviderSessionMetadata) agent.ProviderSessionMetadata {
	out := agent.ProviderSessionMetadata{}
	if len(in.Modes) > 0 {
		out.Modes = append([]string(nil), in.Modes...)
	}
	if len(in.ConfigOptions) > 0 {
		out.ConfigOptions = make([]map[string]interface{}, 0, len(in.ConfigOptions))
		for _, option := range in.ConfigOptions {
			copyOption := make(map[string]interface{}, len(option))
			for k, v := range option {
				copyOption[k] = v
			}
			out.ConfigOptions = append(out.ConfigOptions, copyOption)
		}
	}
	return out
}
