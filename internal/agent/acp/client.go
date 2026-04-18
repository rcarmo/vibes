// Package acp implements the ACP (Agent Client Protocol) provider for Vibes.
//
// It wraps keepmind9/acp-sdk-go to manage stdio-based agent subprocesses
// (copilot --acp, codex-acp, claude --acp) with streaming support.
package acp

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"

	acpclient "github.com/keepmind9/acp-sdk-go/client"
	"github.com/keepmind9/acp-sdk-go/contrib"
	"github.com/keepmind9/acp-sdk-go/schema"
	"github.com/keepmind9/acp-sdk-go/transport"
	"github.com/rcarmo/vibes/internal/agent"
)

// Config configures an ACP agent provider.
type Config struct {
	ID      string   // provider identifier (e.g., "copilot")
	Command string   // agent binary name
	Args    []string // agent binary arguments
	WorkDir string   // working directory for the agent
	Debug   bool     // enable wire logging
}

// Provider implements agent.Provider for ACP agents.
type Provider struct {
	cfg     Config
	conn    *acpclient.Client
	proc    *transport.Process
	events  chan agent.Event
	tracker *contrib.ToolCallTracker
	perms   *contrib.PermissionBroker
	accum   *contrib.SessionAccumulator

	mu     sync.RWMutex
	status agent.ProviderStatus
}

// New creates a new ACP provider with the given configuration.
func New(cfg Config) *Provider {
	return &Provider{
		cfg:    cfg,
		events: make(chan agent.Event, 256),
		status: agent.ProviderStatus{State: "stopped"},
	}
}

func (p *Provider) ID() string { return p.cfg.ID }

func (p *Provider) Events() <-chan agent.Event { return p.events }

func (p *Provider) Status() agent.ProviderStatus {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.status
}

func (p *Provider) setStatus(s agent.ProviderStatus) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.status = s
}

// Initialize spawns the ACP agent subprocess and performs the ACP handshake.
func (p *Provider) Initialize(ctx context.Context) error {
	// Build the command
	args := make([]string, len(p.cfg.Args))
	copy(args, p.cfg.Args)

	slog.Info("spawning ACP agent",
		"id", p.cfg.ID,
		"command", p.cfg.Command,
		"args", strings.Join(args, " "),
	)

	// Spawn the agent subprocess
	proc, err := transport.Spawn(ctx, p.cfg.Command, args...)
	if err != nil {
		return fmt.Errorf("spawn ACP agent %s: %w", p.cfg.ID, err)
	}
	p.proc = proc

	// Create typed client connection
	client := acpclient.New(proc.Conn())
	p.conn = client

	// Initialize contrib helpers
	p.tracker = contrib.NewToolCallTracker()
	p.perms = contrib.NewPermissionBroker()
	p.accum = contrib.NewSessionAccumulator()

	// Register notification handler for session/update
	client.OnNotification("session/update", p.handleSessionUpdate)

	// Register request handler for session/request_permission
	client.OnRequest("session/request_permission", p.handlePermissionRequest)

	// Send ACP initialize
	pv := schema.ProtocolVersion(1)
	initReq := &schema.InitializeRequest{
		ProtocolVersion: &pv,
		ClientInfo:      &schema.Implementation{Name: "vibes-go", Version: "0.1.0"},
		ClientCapabilities: &schema.ClientCapabilities{},
	}

	resp, err := client.Initialize(ctx, initReq)
	if err != nil {
		proc.Kill()
		return fmt.Errorf("ACP initialize: %w", err)
	}

	model := ""
	if resp.AgentInfo != nil {
		model = resp.AgentInfo.Name
	}

	p.setStatus(agent.ProviderStatus{State: "idle", Model: model})
	slog.Info("ACP agent initialized", "id", p.cfg.ID, "agent", model)

	return nil
}

// Prompt sends a user message to the ACP agent.
func (p *Provider) Prompt(ctx context.Context, message string, threadID int64) error {
	p.setStatus(agent.ProviderStatus{State: "busy", Model: p.status.Model})

	// Reset accumulator for new turn
	p.accum.Reset()

	req := &schema.PromptRequest{
		Messages: []schema.PromptMessage{
			{
				Role: "user",
				Content: schema.ContentBlockList{
					schema.TextContentBlock(message),
				},
			},
		},
	}

	resp, err := p.conn.Prompt(ctx, req)

	p.setStatus(agent.ProviderStatus{State: "idle", Model: p.status.Model})

	if err != nil {
		p.events <- agent.Event{Type: "error", Data: err.Error()}
		return err
	}

	// Send final response event
	p.events <- agent.Event{Type: "response", Data: resp}

	return nil
}

// Cancel aborts the current prompt.
func (p *Provider) Cancel() error {
	if p.conn != nil {
		return p.conn.Cancel()
	}
	return nil
}

// Shutdown stops the ACP agent subprocess.
func (p *Provider) Shutdown(ctx context.Context) error {
	p.setStatus(agent.ProviderStatus{State: "stopped"})
	if p.proc != nil {
		return p.proc.Kill()
	}
	return nil
}

// handleSessionUpdate processes streaming session/update notifications.
func (p *Provider) handleSessionUpdate(params interface{}) {
	// Route based on update type to appropriate UI channel
	// This is where draft/thought/plan/tool_call classification happens
	// using metadata only (not content heuristics), per ACP_ROUTING.md

	update, ok := params.(*schema.SessionUpdate)
	if !ok {
		return
	}

	p.accum.Add(update)

	switch {
	case update.Kind == "tool_call" || update.Kind == "tool_call_update":
		p.tracker.Track(update)
		p.events <- agent.Event{Type: "status", Data: update}

	case isThoughtSegment(update):
		p.events <- agent.Event{Type: "thought", Data: update}

	default:
		p.events <- agent.Event{Type: "draft", Data: update}
	}
}

// handlePermissionRequest processes permission requests from the agent.
func (p *Provider) handlePermissionRequest(params interface{}) interface{} {
	p.events <- agent.Event{Type: "permission", Data: params}
	// The permission broker will handle the response asynchronously
	return p.perms.Wait(params)
}

// isThoughtSegment returns true if the update is a thought/plan/segment
// using only metadata fields, not content inspection.
func isThoughtSegment(update *schema.SessionUpdate) bool {
	switch update.Segment {
	case "think", "thought", "thinking", "plan", "intent", "segment":
		return true
	}
	switch update.Channel {
	case "think", "thought", "thinking", "plan":
		return true
	}
	return false
}
