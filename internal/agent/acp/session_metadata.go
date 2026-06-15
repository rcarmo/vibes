package acp

import "github.com/rcarmo/vibes/internal/agent"

const maxSessionMetadataItems = 32

func (p *Provider) setSessionMetadata(metadata agent.ProviderSessionMetadata) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.sessionMetadata = metadata
}

func (p *Provider) mergeSessionMetadata(metadata agent.ProviderSessionMetadata) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.sessionMetadata = mergeSessionMetadata(p.sessionMetadata, metadata)
}

// SessionMetadata returns display-only ACP session/new metadata.
func (p *Provider) SessionMetadata() agent.ProviderSessionMetadata {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return cloneSessionMetadata(p.sessionMetadata)
}

func parseSessionMetadata(result map[string]interface{}) agent.ProviderSessionMetadata {
	metadata := agent.ProviderSessionMetadata{
		Modes:         parseStringList(firstValue(result, "modes", "availableModes"), maxSessionMetadataItems),
		ConfigOptions: parseConfigOptions(firstValue(result, "configOptions", "config_options"), maxSessionMetadataItems),
		Commands:      parseCommandMetadata(firstValue(result, "commands", "availableCommands", "available_commands"), maxSessionMetadataItems),
	}
	if mode, ok := firstValue(result, "currentMode", "current_mode", "mode").(string); ok {
		metadata.CurrentMode = mode
	}
	return metadata
}

func mergeSessionMetadata(current, next agent.ProviderSessionMetadata) agent.ProviderSessionMetadata {
	out := cloneSessionMetadata(current)
	if len(next.Modes) > 0 {
		out.Modes = append([]string(nil), next.Modes...)
	}
	if len(next.ConfigOptions) > 0 {
		out.ConfigOptions = cloneMapList(next.ConfigOptions)
	}
	if len(next.Commands) > 0 {
		out.Commands = cloneMapList(next.Commands)
	}
	if next.CurrentMode != "" {
		out.CurrentMode = next.CurrentMode
	}
	return out
}

func firstValue(m map[string]interface{}, keys ...string) interface{} {
	for _, key := range keys {
		if value, ok := m[key]; ok {
			return value
		}
	}
	return nil
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

func parseCommandMetadata(value interface{}, max int) []map[string]interface{} {
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
		for _, key := range []string{"id", "name", "description", "title"} {
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
	out := agent.ProviderSessionMetadata{CurrentMode: in.CurrentMode}
	if len(in.Modes) > 0 {
		out.Modes = append([]string(nil), in.Modes...)
	}
	if len(in.ConfigOptions) > 0 {
		out.ConfigOptions = cloneMapList(in.ConfigOptions)
	}
	if len(in.Commands) > 0 {
		out.Commands = cloneMapList(in.Commands)
	}
	return out
}

func cloneMapList(in []map[string]interface{}) []map[string]interface{} {
	out := make([]map[string]interface{}, 0, len(in))
	for _, item := range in {
		copyItem := make(map[string]interface{}, len(item))
		for k, v := range item {
			copyItem[k] = v
		}
		out = append(out, copyItem)
	}
	return out
}
