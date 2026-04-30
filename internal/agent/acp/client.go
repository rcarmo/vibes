// Package acp implements the ACP (Agent Client Protocol) provider for Vibes.
//
// It wraps keepmind9/acp-sdk-go to manage stdio-based agent subprocesses
// (copilot-language-server --acp --stdio, codex-acp, claude-agent-acp)
// with streaming support.
package acp

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"

	acpclient "github.com/keepmind9/acp-sdk-go/client"
	"github.com/keepmind9/acp-sdk-go/core"
	"github.com/keepmind9/acp-sdk-go/helpers"
	"github.com/keepmind9/acp-sdk-go/schema"
	"github.com/keepmind9/acp-sdk-go/transport"

	"github.com/rcarmo/vibes/internal/agent"
)

// Config configures an ACP agent provider.
type Config struct {
	ID      string            // provider identifier (e.g., "copilot")
	Command string            // agent binary name (e.g., "copilot-language-server")
	Args    []string          // agent binary arguments (e.g., ["--acp", "--stdio"])
	WorkDir string            // working directory for the agent
	Env     map[string]string // additional environment variables
}

// Provider implements agent.Provider for ACP agents.
type Provider struct {
	cfg       Config
	conn      *acpclient.ClientSideConnection
	proc      *transport.Subprocess
	events    chan agent.Event
	sessionID string

	// Per-turn state for tool call tracking and content classification.
	turnMu    sync.Mutex
	toolCalls map[string]*schema.ToolCall

	mu     sync.RWMutex
	status agent.ProviderStatus
}

// New creates a new ACP provider with the given configuration.
func New(cfg Config) *Provider {
	return &Provider{
		cfg:       cfg,
		events:    make(chan agent.Event, 256),
		toolCalls: make(map[string]*schema.ToolCall),
		status:    agent.ProviderStatus{State: "stopped"},
	}
}

func (p *Provider) ID() string                 { return p.cfg.ID }
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
	slog.Info("spawning ACP agent",
		"id", p.cfg.ID,
		"command", p.cfg.Command,
		"args", strings.Join(p.cfg.Args, " "),
	)

	// Build spawn options
	opts := []transport.SpawnOption{transport.WithArgs(p.cfg.Args...)}
	if p.cfg.WorkDir != "" {
		opts = append(opts, transport.WithCwd(p.cfg.WorkDir))
	}
	if len(p.cfg.Env) > 0 {
		opts = append(opts, transport.WithEnv(p.cfg.Env))
	}

	proc, err := transport.Spawn(p.cfg.Command, opts...)
	if err != nil {
		return fmt.Errorf("spawn ACP agent %s: %w", p.cfg.ID, err)
	}
	p.proc = proc

	// Connect using the core helper. The clientImpl receives session updates.
	impl := &clientImpl{provider: p, Base: &acpclient.Base{}}
	conn := core.ConnectToAgent(impl, proc)
	go conn.ReceiveLoop()
	p.conn = conn

	// Perform ACP initialize handshake
	pv := schema.ProtocolVersion(1)
	resp, err := conn.Initialize(&schema.InitializeRequest{
		ProtocolVersion:    &pv,
		ClientCapabilities: &schema.ClientCapabilities{},
		ClientInfo:         &schema.Implementation{Name: "vibes-go", Version: "0.1.0"},
	})
	if err != nil {
		proc.Close()
		return fmt.Errorf("ACP initialize: %w", err)
	}

	model := ""
	if resp.AgentInfo != nil {
		model = resp.AgentInfo.Name
	}

	// Create a new session
	session, err := conn.NewSession(&schema.NewSessionRequest{
		McpServers: []*schema.McpServer{},
	})
	if err != nil {
		proc.Close()
		return fmt.Errorf("ACP new_session: %w", err)
	}
	if session.SessionId != nil {
		p.sessionID = string(*session.SessionId)
	}

	p.setStatus(agent.ProviderStatus{State: "idle", Model: model})
	slog.Info("ACP agent initialized",
		"id", p.cfg.ID,
		"agent", model,
		"protocol", *resp.ProtocolVersion,
		"session", p.sessionID,
	)

	return nil
}

// Prompt sends a user message to the ACP agent.
func (p *Provider) Prompt(ctx context.Context, message string, threadID int64) error {
	if p.conn == nil || p.sessionID == "" {
		return fmt.Errorf("ACP agent %s is not initialized", p.cfg.ID)
	}

	p.setStatus(agent.ProviderStatus{State: "busy", Model: p.status.Model})
	defer p.setStatus(agent.ProviderStatus{State: "idle", Model: p.status.Model})

	// Reset per-turn tool call state
	p.turnMu.Lock()
	p.toolCalls = make(map[string]*schema.ToolCall)
	p.turnMu.Unlock()

	block := helpers.TextBlock(message)
	sessID := schema.SessionId(p.sessionID)
	resp, err := p.conn.Prompt(&schema.PromptRequest{
		SessionId: &sessID,
		Prompt:    []*schema.ContentBlock{&block},
	})

	if err != nil {
		p.events <- agent.Event{Type: "error", Data: err.Error()}
		return err
	}

	p.events <- agent.Event{Type: "response", Data: resp}
	return nil
}

// Cancel aborts the current prompt.
func (p *Provider) Cancel() error {
	if p.conn == nil || p.sessionID == "" {
		return nil
	}
	return p.conn.Cancel(p.sessionID)
}

// Shutdown stops the ACP agent subprocess.
func (p *Provider) Shutdown(ctx context.Context) error {
	p.setStatus(agent.ProviderStatus{State: "stopped"})
	if p.conn != nil {
		p.conn.Close()
	}
	if p.proc != nil {
		return p.proc.Close()
	}
	return nil
}

// clientImpl implements the ACP Client interface to receive session updates.
type clientImpl struct {
	*acpclient.Base
	provider *Provider
}

// SessionUpdate is called for every streaming session/update notification.
// We classify by metadata only (per docs/ACP_ROUTING.md) and fan out to events.
func (c *clientImpl) SessionUpdate(_ context.Context, notif *schema.SessionNotification) error {
	switch notif.Update.SessionUpdate {
	case schema.SessionUpdateKindAgentMessageChunk:
		c.provider.events <- agent.Event{Type: "draft", Data: notif.Update.AgentMessageChunk}

	case schema.SessionUpdateKindAgentThoughtChunk:
		c.provider.events <- agent.Event{Type: "thought", Data: notif.Update.AgentThoughtChunk}

	case schema.SessionUpdateKindToolCall:
		if notif.Update.ToolCall != nil {
			c.provider.turnMu.Lock()
			id := ""
			if notif.Update.ToolCall.ToolCallId != nil {
				id = string(*notif.Update.ToolCall.ToolCallId)
			}
			c.provider.toolCalls[id] = notif.Update.ToolCall
			c.provider.turnMu.Unlock()
			c.provider.events <- agent.Event{Type: "status", Data: notif.Update.ToolCall}
		}

	case schema.SessionUpdateKindToolCallUpdate:
		if notif.Update.ToolCallUpdate != nil {
			c.provider.events <- agent.Event{Type: "status", Data: notif.Update.ToolCallUpdate}
		}

	case schema.SessionUpdateKindPlan:
		if notif.Update.Plan != nil {
			c.provider.events <- agent.Event{Type: "plan", Data: notif.Update.Plan}
		}
	}
	return nil
}
