package mcpadapter

import "testing"

func TestRegistryDiscoverDefaultReadOnlyTools(t *testing.T) {
	registry := NewRegistry()
	tools := registry.Discover(DefaultEnvironment())
	byName := map[string]ToolDescriptor{}
	for _, tool := range tools {
		byName[tool.Name] = tool
		if !tool.Enabled {
			t.Fatalf("discovered disabled tool: %#v", tool)
		}
	}
	for _, name := range []string{
		"vibes.adapter_capabilities",
		"vibes.list_providers",
		"vibes.get_provider",
		"vibes.get_session_metadata",
		"vibes.get_context_usage",
		"vibes.get_recent_local_service_audit",
		"vibes.get_workspace_tree",
		"vibes.get_workspace_file_info",
		"vibes.read_workspace_file_slice",
		"vibes.search_timeline",
	} {
		if _, ok := byName[name]; !ok {
			t.Fatalf("default discovery missing %s; got %#v", name, tools)
		}
	}
	for _, name := range []string{"vibes.open_workspace_file", "vibes.terminal_create", "vibes.send_work_session_message"} {
		if _, ok := byName[name]; ok {
			t.Fatalf("default discovery unexpectedly includes %s", name)
		}
	}
}

func TestRegistryDiscoverDynamicTools(t *testing.T) {
	registry := NewRegistry()
	tools := registry.Discover(Environment{
		WorkspaceAvailable:    true,
		ProviderIntrospection: true,
		AuditAvailable:        true,
		UIBridgeAvailable:     true,
		WriteEnabled:          true,
		TerminalEnabled:       true,
		SessionRegistry:       true,
	})
	byName := map[string]ToolDescriptor{}
	for _, tool := range tools {
		byName[tool.Name] = tool
	}
	for _, name := range []string{"vibes.open_workspace_file", "vibes.request_write_file", "vibes.terminal_create", "vibes.list_work_sessions", "vibes.send_work_session_message"} {
		if _, ok := byName[name]; !ok {
			t.Fatalf("dynamic discovery missing %s", name)
		}
	}
}

func TestRegistryContainsPlannedToolsAndStubHandlers(t *testing.T) {
	registry := NewRegistry()
	if len(registry.All()) < 10 {
		t.Fatalf("registry surface too small: %d", len(registry.All()))
	}
	handler, ok := registry.HandlerFor("vibes.list_providers")
	if !ok {
		t.Fatal("handler missing")
	}
	if _, err := handler(nil, nil); err != ErrToolNotImplemented {
		t.Fatalf("handler error = %v", err)
	}
	if _, ok := registry.HandlerFor("missing"); ok {
		t.Fatal("missing tool had handler")
	}
}

func TestServerCapabilitiesAreSerializable(t *testing.T) {
	server := NewServer(nil, nil, nil)
	caps := server.Capabilities()
	if caps["name"] != "vibes" || caps["version"] == "" || caps["tools"] == nil || caps["all_tools"] == nil {
		t.Fatalf("capabilities = %#v", caps)
	}
}
