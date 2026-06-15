package acp

import "testing"

func TestParseSessionMetadata(t *testing.T) {
	metadata := parseSessionMetadata(map[string]interface{}{
		"modes":       []interface{}{"default", "plan", 42, ""},
		"currentMode": "plan",
		"configOptions": []interface{}{
			map[string]interface{}{"id": "model", "name": "Model", "type": "select", "values": []interface{}{"a", "b"}, "unsafe": "drop"},
			"bad",
		},
		"availableCommands": []interface{}{
			map[string]interface{}{"id": "explain", "name": "Explain", "description": "Explain selection", "unsafe": "drop"},
		},
	})
	if len(metadata.Modes) != 2 || metadata.Modes[0] != "default" || metadata.Modes[1] != "plan" {
		t.Fatalf("modes = %#v", metadata.Modes)
	}
	if metadata.CurrentMode != "plan" {
		t.Fatalf("current mode = %q", metadata.CurrentMode)
	}
	if len(metadata.ConfigOptions) != 1 {
		t.Fatalf("config options = %#v", metadata.ConfigOptions)
	}
	if metadata.ConfigOptions[0]["id"] != "model" || metadata.ConfigOptions[0]["unsafe"] != nil {
		t.Fatalf("config option was not sanitized: %#v", metadata.ConfigOptions[0])
	}
	if len(metadata.Commands) != 1 || metadata.Commands[0]["id"] != "explain" || metadata.Commands[0]["unsafe"] != nil {
		t.Fatalf("commands were not sanitized: %#v", metadata.Commands)
	}
}

func TestSessionMetadataReturnsClone(t *testing.T) {
	p := New(Config{})
	p.setSessionMetadata(parseSessionMetadata(map[string]interface{}{
		"modes":         []interface{}{"default"},
		"configOptions": []interface{}{map[string]interface{}{"id": "mode"}},
		"commands":      []interface{}{map[string]interface{}{"id": "explain"}},
	}))
	metadata := p.SessionMetadata()
	metadata.Modes[0] = "mutated"
	metadata.ConfigOptions[0]["id"] = "mutated"
	metadata.Commands[0]["id"] = "mutated"

	again := p.SessionMetadata()
	if again.Modes[0] != "default" || again.ConfigOptions[0]["id"] != "mode" || again.Commands[0]["id"] != "explain" {
		t.Fatalf("session metadata was mutated: %#v", again)
	}
}

func TestMergeSessionMetadata(t *testing.T) {
	current := parseSessionMetadata(map[string]interface{}{
		"modes":         []interface{}{"default"},
		"configOptions": []interface{}{map[string]interface{}{"id": "mode"}},
	})
	next := parseSessionMetadata(map[string]interface{}{
		"current_mode":      "plan",
		"availableCommands": []interface{}{map[string]interface{}{"id": "explain"}},
	})
	merged := mergeSessionMetadata(current, next)
	if len(merged.Modes) != 1 || merged.Modes[0] != "default" {
		t.Fatalf("modes should be preserved: %#v", merged.Modes)
	}
	if len(merged.ConfigOptions) != 1 || merged.ConfigOptions[0]["id"] != "mode" {
		t.Fatalf("config should be preserved: %#v", merged.ConfigOptions)
	}
	if merged.CurrentMode != "plan" || len(merged.Commands) != 1 || merged.Commands[0]["id"] != "explain" {
		t.Fatalf("metadata not merged: %#v", merged)
	}
}
