// Package mcpadapter maps the bundled Vibes MCP adapter surface.
//
// The package intentionally starts with registry/contracts and disabled stubs.
// Future passes should implement handlers in the order encoded by Phase and
// Safety so the tool list itself is the durable implementation plan.
package mcpadapter

import (
	"context"
	"errors"
	"sort"
)

// ToolPhase documents the implementation rollout for a bundled Vibes MCP tool.
type ToolPhase string

const (
	PhaseReadOnly     ToolPhase = "read_only"
	PhaseUICommand    ToolPhase = "ui_command"
	PhaseMutating     ToolPhase = "mutating"
	PhaseTerminal     ToolPhase = "terminal"
	PhaseCrossSession ToolPhase = "cross_session"
)

// ToolSafety describes the local safety posture required before a tool can be
// advertised. This is separate from MCP protocol support: a tool can exist in
// the registry while remaining undiscoverable until its safety gate is present.
type ToolSafety string

const (
	SafetyAlwaysAvailable ToolSafety = "always_available"
	SafetyWorkspaceRead   ToolSafety = "workspace_read"
	SafetyUIBridge        ToolSafety = "ui_bridge"
	SafetyWriteApproval   ToolSafety = "write_approval"
	SafetyTerminalPolicy  ToolSafety = "terminal_policy"
	SafetySessionRegistry ToolSafety = "session_registry"
)

// ContextBudget defines context-efficiency defaults for a tool. Handlers must
// prefer compact responses and require explicit follow-up calls for large data.
type ContextBudget struct {
	MaxResults int `json:"max_results,omitempty"`
	MaxBytes   int `json:"max_bytes,omitempty"`
	MaxLines   int `json:"max_lines,omitempty"`
}

// ToolDescriptor is the durable map of the bundled Vibes MCP surface.
type ToolDescriptor struct {
	Name        string        `json:"name"`
	Title       string        `json:"title"`
	Description string        `json:"description"`
	Phase       ToolPhase     `json:"phase"`
	Safety      ToolSafety    `json:"safety"`
	ReadOnly    bool          `json:"read_only"`
	Enabled     bool          `json:"enabled"`
	Budget      ContextBudget `json:"budget,omitempty"`
	TODO        string        `json:"todo,omitempty"`
}

// Environment is the runtime capability snapshot used for dynamic discovery.
// Keep this deliberately small and backend-neutral; app/ACP code can fill it
// from config, provider descriptors, DB availability and frontend bridge state.
type Environment struct {
	WorkspaceAvailable    bool
	ProviderIntrospection bool
	AuditAvailable        bool
	UIBridgeAvailable     bool
	WriteEnabled          bool
	TerminalEnabled       bool
	SessionRegistry       bool
}

// DefaultEnvironment is the conservative discovery state for a normal Vibes
// server process before app-specific dependencies are wired into an MCP server.
func DefaultEnvironment() Environment {
	return Environment{
		WorkspaceAvailable:    true,
		ProviderIntrospection: true,
		AuditAvailable:        true,
	}
}

// Registry contains all planned MCP tools, including disabled future tools.
type Registry struct {
	tools []ToolDescriptor
}

// NewRegistry returns the full planned Vibes MCP adapter surface. The Enabled
// field is dynamic and recalculated by Discover.
func NewRegistry() Registry {
	return Registry{tools: defaultTools()}
}

// All returns every known tool descriptor, including planned/disabled tools.
func (r Registry) All() []ToolDescriptor {
	out := append([]ToolDescriptor(nil), r.tools...)
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

// Discover returns only tools enabled by the provided environment.
func (r Registry) Discover(env Environment) []ToolDescriptor {
	out := []ToolDescriptor{}
	for _, tool := range r.tools {
		tool.Enabled = toolEnabled(tool, env)
		if tool.Enabled {
			out = append(out, tool)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

func toolEnabled(tool ToolDescriptor, env Environment) bool {
	switch tool.Safety {
	case SafetyAlwaysAvailable:
		return env.ProviderIntrospection || tool.Name == "vibes.adapter_capabilities"
	case SafetyWorkspaceRead:
		return env.WorkspaceAvailable
	case SafetyUIBridge:
		return env.UIBridgeAvailable
	case SafetyWriteApproval:
		return env.WriteEnabled
	case SafetyTerminalPolicy:
		return env.TerminalEnabled
	case SafetySessionRegistry:
		return env.SessionRegistry
	default:
		return false
	}
}

var ErrToolNotImplemented = errors.New("vibes MCP tool handler not implemented yet")

// Handler is the common signature future MCP tool implementations should use
// after protocol glue decodes arguments. Return values must be compact and
// serializable to JSON-like MCP content.
type Handler func(context.Context, map[string]interface{}) (interface{}, error)

// HandlerFor returns a disabled stub for every mapped tool. This lets future
// MCP protocol wiring call through a stable registry while individual tools are
// implemented incrementally.
func (r Registry) HandlerFor(name string) (Handler, bool) {
	for _, tool := range r.tools {
		if tool.Name == name {
			return func(context.Context, map[string]interface{}) (interface{}, error) {
				return nil, ErrToolNotImplemented
			}, true
		}
	}
	return nil, false
}

func defaultTools() []ToolDescriptor {
	return []ToolDescriptor{
		{
			Name:        "vibes.adapter_capabilities",
			Title:       "Describe Vibes MCP adapter capabilities",
			Description: "Return adapter version, dynamic discovery rules, context budgets, and unavailable tool reasons.",
			Phase:       PhaseReadOnly,
			Safety:      SafetyAlwaysAvailable,
			ReadOnly:    true,
			TODO:        "Implement as the first MCP protocol handler; should never require app DB access.",
		},
		{
			Name:        "vibes.list_providers",
			Title:       "List Vibes providers",
			Description: "Return active provider, configured providers, status, model, capabilities and compact session metadata.",
			Phase:       PhaseReadOnly,
			Safety:      SafetyAlwaysAvailable,
			ReadOnly:    true,
			Budget:      ContextBudget{MaxResults: 20, MaxBytes: 20_000},
			TODO:        "Wire to agent.Registry.Descriptors with compact mode by default.",
		},
		{
			Name:        "vibes.get_provider",
			Title:       "Get one Vibes provider",
			Description: "Return one provider descriptor, negotiated ACP metadata, current model/status and context usage.",
			Phase:       PhaseReadOnly,
			Safety:      SafetyAlwaysAvailable,
			ReadOnly:    true,
			Budget:      ContextBudget{MaxBytes: 12_000},
			TODO:        "Wire to agent.Registry.Descriptor.",
		},
		{
			Name:        "vibes.get_session_metadata",
			Title:       "Get provider session metadata",
			Description: "Return sanitized modes, current mode, config options and available command metadata for a provider.",
			Phase:       PhaseReadOnly,
			Safety:      SafetyAlwaysAvailable,
			ReadOnly:    true,
			Budget:      ContextBudget{MaxBytes: 12_000},
			TODO:        "Use ProviderDescriptor.SessionMetadata; do not execute commands or mutate mode.",
		},
		{
			Name:        "vibes.get_context_usage",
			Title:       "Get context usage",
			Description: "Return current provider context window usage when known.",
			Phase:       PhaseReadOnly,
			Safety:      SafetyAlwaysAvailable,
			ReadOnly:    true,
			Budget:      ContextBudget{MaxBytes: 4_000},
			TODO:        "Wire to ProviderStatus.ContextPct via registry.Active/Descriptor.",
		},
		{
			Name:        "vibes.get_recent_local_service_audit",
			Title:       "Get recent local-service audit events",
			Description: "Return recent sanitized local-service audit rows without content, previews, secrets or raw environment.",
			Phase:       PhaseReadOnly,
			Safety:      SafetyAlwaysAvailable,
			ReadOnly:    true,
			Budget:      ContextBudget{MaxResults: 50, MaxBytes: 20_000},
			TODO:        "Wire to db.GetLocalServiceAudits; default compact, newest first.",
		},
		{
			Name:        "vibes.get_workspace_tree",
			Title:       "Get workspace tree",
			Description: "Return a bounded workspace tree rooted at a relative path.",
			Phase:       PhaseReadOnly,
			Safety:      SafetyWorkspaceRead,
			ReadOnly:    true,
			Budget:      ContextBudget{MaxResults: 200, MaxBytes: 30_000},
			TODO:        "Reuse workspace route confinement helpers; include pagination/depth limits.",
		},
		{
			Name:        "vibes.get_workspace_file_info",
			Title:       "Get workspace file info",
			Description: "Return path, size, mtime, type hint and hashes so agents can avoid rereading unchanged content.",
			Phase:       PhaseReadOnly,
			Safety:      SafetyWorkspaceRead,
			ReadOnly:    true,
			Budget:      ContextBudget{MaxBytes: 8_000},
			TODO:        "Implement metadata-only stat/hash helper; do not return file content.",
		},
		{
			Name:        "vibes.read_workspace_file_slice",
			Title:       "Read workspace file slice",
			Description: "Return a bounded text slice by line/byte limits; never return whole large files by default.",
			Phase:       PhaseReadOnly,
			Safety:      SafetyWorkspaceRead,
			ReadOnly:    true,
			Budget:      ContextBudget{MaxBytes: 20_000, MaxLines: 200},
			TODO:        "Reuse ACP read_text_file/root confinement rules and require explicit path + range.",
		},
		{
			Name:        "vibes.search_timeline",
			Title:       "Search Vibes timeline",
			Description: "Return compact matching interactions with ids, timestamps, backend metadata and snippets.",
			Phase:       PhaseReadOnly,
			Safety:      SafetyAlwaysAvailable,
			ReadOnly:    true,
			Budget:      ContextBudget{MaxResults: 20, MaxBytes: 20_000},
			TODO:        "Wire to db.SearchInteractions; excerpt results only.",
		},
		{
			Name:        "vibes.open_workspace_file",
			Title:       "Open workspace file in UI",
			Description: "Ask the active Vibes UI to open a workspace file in an editor tab or popout via SSE ui_command.",
			Phase:       PhaseUICommand,
			Safety:      SafetyUIBridge,
			ReadOnly:    false,
			Budget:      ContextBudget{MaxBytes: 4_000},
			TODO:        "Requires SSE ui_command bridge, workspace path validation, no arbitrary URL/JS.",
		},
		{
			Name:        "vibes.show_workspace",
			Title:       "Show workspace pane",
			Description: "Ask the active Vibes UI to show/focus the workspace explorer.",
			Phase:       PhaseUICommand,
			Safety:      SafetyUIBridge,
			ReadOnly:    false,
			Budget:      ContextBudget{MaxBytes: 2_000},
			TODO:        "Requires frontend ui_command handler; no filesystem mutation.",
		},
		{
			Name:        "vibes.request_write_file",
			Title:       "Request a guarded workspace write",
			Description: "Future high-level write request; prefer ACP fs/write_text_file unless MCP-only providers need the path.",
			Phase:       PhaseMutating,
			Safety:      SafetyWriteApproval,
			ReadOnly:    false,
			Budget:      ContextBudget{MaxBytes: 20_000},
			TODO:        "Do not implement until duplicate semantics with ACP fs/write_text_file are resolved.",
		},
		{
			Name:        "vibes.terminal_create",
			Title:       "Create guarded terminal session",
			Description: "Future terminal session creation behind ACP terminal policy, env allowlist, limits and audit.",
			Phase:       PhaseTerminal,
			Safety:      SafetyTerminalPolicy,
			ReadOnly:    false,
			TODO:        "Terminal policy scaffolding must land before discovery enables this tool.",
		},
		{
			Name:        "vibes.list_work_sessions",
			Title:       "List Vibes work sessions",
			Description: "Future cross-session registry introspection for multi-agent coordination.",
			Phase:       PhaseCrossSession,
			Safety:      SafetySessionRegistry,
			ReadOnly:    true,
			Budget:      ContextBudget{MaxResults: 20, MaxBytes: 20_000},
			TODO:        "Requires explicit Vibes work-session registry; do not infer from flat timeline.",
		},
		{
			Name:        "vibes.send_work_session_message",
			Title:       "Send message to a Vibes work session",
			Description: "Future cross-session chat/queue/steer primitive after session registry exists.",
			Phase:       PhaseCrossSession,
			Safety:      SafetySessionRegistry,
			ReadOnly:    false,
			TODO:        "Requires explicit target session registry and queue/steer semantics.",
		},
	}
}
