package acp

import "testing"

func TestParseSessionMetadata(t *testing.T) {
	metadata := parseSessionMetadata(map[string]interface{}{
		"modes": []interface{}{"default", "plan", 42, ""},
		"configOptions": []interface{}{
			map[string]interface{}{"id": "model", "name": "Model", "type": "select", "values": []interface{}{"a", "b"}, "unsafe": "drop"},
			"bad",
		},
	})
	if len(metadata.Modes) != 2 || metadata.Modes[0] != "default" || metadata.Modes[1] != "plan" {
		t.Fatalf("modes = %#v", metadata.Modes)
	}
	if len(metadata.ConfigOptions) != 1 {
		t.Fatalf("config options = %#v", metadata.ConfigOptions)
	}
	if metadata.ConfigOptions[0]["id"] != "model" || metadata.ConfigOptions[0]["unsafe"] != nil {
		t.Fatalf("config option was not sanitized: %#v", metadata.ConfigOptions[0])
	}
}

func TestSessionMetadataReturnsClone(t *testing.T) {
	p := New(Config{})
	p.setSessionMetadata(parseSessionMetadata(map[string]interface{}{
		"modes":         []interface{}{"default"},
		"configOptions": []interface{}{map[string]interface{}{"id": "mode"}},
	}))
	metadata := p.SessionMetadata()
	metadata.Modes[0] = "mutated"
	metadata.ConfigOptions[0]["id"] = "mutated"

	again := p.SessionMetadata()
	if again.Modes[0] != "default" || again.ConfigOptions[0]["id"] != "mode" {
		t.Fatalf("session metadata was mutated: %#v", again)
	}
}
