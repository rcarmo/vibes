package agent

// PiCapabilities returns capabilities exposed by the native Pi RPC backend.
func PiCapabilities() ProviderCapabilities {
	return ProviderCapabilities{
		StreamingDrafts:    true,
		StreamingThoughts:  true,
		ToolEvents:         true,
		PermissionRequests: true,
		ModelList:          true,
		ModelSwitch:        true,
		ThinkingLevels:     []string{"off", "minimal", "low", "medium", "high", "xhigh"},
		SessionReset:       true,
		SessionCompact:     true,
		SessionRename:      true,
		SessionStats:       true,
		MessageHistory:     true,
		CommandsList:       true,
		Steering:           true,
		FollowUpQueue:      true,
		WorkingDirectory:   true,
		ToolsMode:          []string{"none", "readonly", "full"},
	}
}

// ACPCapabilities returns the conservative common capability set for ACP
// backends. Individual ACP providers can be refined later if they expose more.
func ACPCapabilities() ProviderCapabilities {
	return ProviderCapabilities{
		StreamingDrafts:    true,
		StreamingThoughts:  false,
		ToolEvents:         true,
		PermissionRequests: false,
		ModelList:          false,
		ModelSwitch:        false,
		SessionReset:       false,
		CommandsList:       false,
		Steering:           false,
		FollowUpQueue:      false,
		WorkingDirectory:   true,
		MCPServers:         true,
	}
}
