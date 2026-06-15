package acp

import (
	"encoding/json"
	"math"

	"github.com/rcarmo/vibes/internal/agent"
)

func stringFromRaw(raw json.RawMessage) string {
	if len(raw) == 0 {
		return ""
	}
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		return s
	}
	return ""
}

func (p *Provider) applySessionUpdateMetadata(update map[string]interface{}) {
	metadata := parseSessionMetadata(update)
	if len(metadata.Modes) > 0 || len(metadata.ConfigOptions) > 0 || len(metadata.Commands) > 0 || metadata.CurrentMode != "" {
		p.mergeSessionMetadata(metadata)
	}
	if pct, ok := contextPercentFromUpdate(update); ok {
		p.mu.Lock()
		status := p.status
		status.ContextPct = pct
		p.status = status
		p.mu.Unlock()
	}
}

func contextPercentFromUpdate(update map[string]interface{}) (float64, bool) {
	for _, key := range []string{"contextPct", "context_pct", "pct", "percent"} {
		if value, ok := numberValue(update[key]); ok {
			return normalizeContextPct(value), true
		}
	}
	for _, key := range []string{"usage", "context", "contextWindow", "context_window"} {
		m, ok := update[key].(map[string]interface{})
		if !ok {
			continue
		}
		for _, pctKey := range []string{"contextPct", "context_pct", "pct", "percent"} {
			if value, ok := numberValue(m[pctKey]); ok {
				return normalizeContextPct(value), true
			}
		}
		used, usedOK := numberValue(firstValue(m, "used", "tokens", "inputTokens", "input_tokens"))
		total, totalOK := numberValue(firstValue(m, "total", "limit", "contextWindow", "context_window"))
		if usedOK && totalOK && total > 0 {
			return clamp01(used / total), true
		}
	}
	return 0, false
}

func numberValue(value interface{}) (float64, bool) {
	switch v := value.(type) {
	case float64:
		return v, !math.IsNaN(v) && !math.IsInf(v, 0)
	case float32:
		f := float64(v)
		return f, !math.IsNaN(f) && !math.IsInf(f, 0)
	case int:
		return float64(v), true
	case int64:
		return float64(v), true
	case json.Number:
		f, err := v.Float64()
		return f, err == nil && !math.IsNaN(f) && !math.IsInf(f, 0)
	default:
		return 0, false
	}
}

func normalizeContextPct(value float64) float64 {
	if value > 1 {
		value = value / 100
	}
	return clamp01(value)
}

func clamp01(value float64) float64 {
	if value < 0 {
		return 0
	}
	if value > 1 {
		return 1
	}
	return value
}

func safeSessionUpdateEvent(kind string, update map[string]interface{}) map[string]interface{} {
	out := map[string]interface{}{}
	if kind != "" {
		out["kind"] = kind
	}
	for _, key := range []string{"sessionId", "session_id", "currentMode", "current_mode"} {
		if value, ok := update[key].(string); ok && value != "" {
			out[key] = value
		}
	}
	if pct, ok := contextPercentFromUpdate(update); ok {
		out["context_pct"] = pct
	}
	metadata := parseSessionMetadata(update)
	if len(metadata.Modes) > 0 || len(metadata.ConfigOptions) > 0 || len(metadata.Commands) > 0 || metadata.CurrentMode != "" {
		out["session_metadata"] = agent.ProviderSessionMetadata{
			Modes:         metadata.Modes,
			ConfigOptions: metadata.ConfigOptions,
			Commands:      metadata.Commands,
			CurrentMode:   metadata.CurrentMode,
		}
	}
	return out
}
