// Package acp implements the ACP (Agent Client Protocol) provider for Vibes.
//
// Uses raw JSON-RPC 2.0 over stdio instead of the acp-sdk-go typed client,
// because the SDK's strict union schema rejects valid responses from several
// agents (OpenCode, Copilot) that omit the 'type' discriminator on authMethods.
package acp

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strings"
	"sync"
	"sync/atomic"

	"github.com/keepmind9/acp-sdk-go/transport"
	"github.com/rcarmo/vibes/internal/agent"
)

// Config configures an ACP agent provider.
type Config struct {
	ID                    string
	Command               string
	Args                  []string
	WorkDir               string
	Env                   map[string]string
	Debug                 bool
	MCPServers            []MCPServer
	FSReadTextEnabled     bool
	FSRoot                string
	FSReadTextMaxBytes    int64
	FSWriteTextEnabled    bool
	FSWriteRoot           string
	FSWriteTextMaxBytes   int64
	FSWriteAllowOverwrite bool
}

// Provider implements agent.Provider for ACP agents using raw JSON-RPC.
type Provider struct {
	cfg       Config
	proc      *transport.Subprocess
	writer    io.Writer
	scanner   *bufio.Scanner
	events    chan agent.Event
	sessionID string
	nextID    atomic.Int64
	pending   sync.Map
	writeMu   sync.Mutex

	// Accumulated draft text for the current turn
	draftMu   sync.Mutex
	draftText strings.Builder

	mu                        sync.RWMutex
	status                    agent.ProviderStatus
	capabilities              AgentCapabilities
	sessionMetadata           agent.ProviderSessionMetadata
	permissionHandler         PermissionHandler
	localServiceAuditRecorder LocalServiceAuditRecorder
}

func New(cfg Config) *Provider {
	return &Provider{
		cfg:    cfg,
		events: make(chan agent.Event, 256),
		status: agent.ProviderStatus{State: "stopped"},
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

func (p *Provider) setCapabilities(caps AgentCapabilities) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.capabilities = caps
}

func (p *Provider) negotiatedCapabilities() AgentCapabilities {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.capabilities
}

func (p *Provider) setSessionID(sessionID string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.sessionID = sessionID
}

func (p *Provider) currentSessionID() string {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.sessionID
}

func (p *Provider) Capabilities() agent.ProviderCapabilities {
	caps := p.negotiatedCapabilities()
	base := agent.ACPCapabilities()
	base.StreamingThoughts = true
	base.PromptImages = caps.Prompt.Image
	base.PromptAudio = caps.Prompt.Audio
	base.EmbeddedContext = caps.Prompt.EmbeddedContext
	base.MCPServers = true
	base.MCPHTTP = caps.MCP.HTTP
	base.MCPSSE = caps.MCP.SSE
	base.SessionList = caps.Session.List
	base.SessionResume = caps.Session.Resume
	base.SessionClose = caps.Session.Close
	base.FSReadTextFile = p.cfg.FSReadTextEnabled
	base.FSWriteTextFile = p.cfg.FSWriteTextEnabled
	base.TerminalServices = false
	return base
}

// Initialize spawns the agent, performs the ACP handshake, and creates a session.
func (p *Provider) Initialize(ctx context.Context) error {
	slog.Info("spawning ACP agent", "id", p.cfg.ID, "command", p.cfg.Command, "args", strings.Join(p.cfg.Args, " "))

	opts := []transport.SpawnOption{transport.WithArgs(p.cfg.Args...)}
	if p.cfg.WorkDir != "" {
		opts = append(opts, transport.WithCwd(p.cfg.WorkDir))
	}
	if len(p.cfg.Env) > 0 {
		opts = append(opts, transport.WithEnv(p.cfg.Env))
	}

	proc, err := transport.Spawn(p.cfg.Command, opts...)
	if err != nil {
		return fmt.Errorf("spawn: %w", err)
	}
	p.proc = proc
	p.writer = proc.Stdin
	p.scanner = bufio.NewScanner(proc.Stdout)
	p.scanner.Buffer(make([]byte, 1<<20), 1<<20) // 1 MB lines

	// Initialize
	initResult, err := p.sendRequest("initialize", map[string]interface{}{
		"protocolVersion":    1,
		"clientInfo":         map[string]string{"name": "vibes-go", "version": "0.1.0"},
		"clientCapabilities": p.clientCapabilities(),
	})
	if err != nil {
		proc.Close()
		return fmt.Errorf("initialize: %w", err)
	}

	caps := parseCapabilities(initResult)
	p.setCapabilities(caps)
	model := caps.AgentInfo.Name

	// Start receive loop (must be after init since init reads synchronously)
	go p.receiveLoop()

	// Create session
	cwd := p.cfg.WorkDir
	if cwd == "" {
		cwd, _ = os.Getwd()
	}
	sessResult, err := p.sendRequestAsync("session/new", p.sessionNewParams(cwd, caps))
	if err != nil {
		slog.Warn("new_session failed (agent may need auth)", "id", p.cfg.ID, "error", err)
	} else if result, ok := sessResult.(map[string]interface{}); ok {
		if sid, ok := result["sessionId"].(string); ok {
			p.setSessionID(sid)
		}
		p.setSessionMetadata(parseSessionMetadata(result))
	}

	p.setStatus(agent.ProviderStatus{State: "idle", Model: model})
	slog.Info("ACP agent initialized", "id", p.cfg.ID, "agent", model, "session", p.currentSessionID())
	return nil
}

// Prompt sends a user message to the ACP agent.
func (p *Provider) Prompt(ctx context.Context, message string, threadID int64) error {
	return p.PromptRequest(ctx, agent.PromptRequest{Text: message, ThreadID: threadID})
}

// PromptRequest sends a prompt envelope to the ACP agent.
func (p *Provider) PromptRequest(ctx context.Context, req agent.PromptRequest) error {
	if p.writer == nil {
		return fmt.Errorf("ACP agent %s is not initialized", p.cfg.ID)
	}
	p.setStatus(agent.ProviderStatus{State: "busy", Model: p.status.Model})
	defer p.setStatus(agent.ProviderStatus{State: "idle", Model: p.status.Model})

	// Reset draft accumulator
	p.draftMu.Lock()
	p.draftText.Reset()
	p.draftMu.Unlock()

	sessionID := p.currentSessionID()
	params := map[string]interface{}{
		"prompt": renderPromptBlocks(req),
	}
	if sessionID != "" {
		params["sessionId"] = sessionID
	}

	_, err := p.sendRequestAsync("session/prompt", params)
	if err != nil {
		p.events <- agent.Event{Type: "error", Data: err.Error()}
		return err
	}
	return nil
}

// Cancel aborts the current prompt.
func (p *Provider) Cancel() error {
	sessionID := p.currentSessionID()
	if sessionID == "" {
		return nil
	}
	return p.sendNotification("session/cancel", map[string]interface{}{
		"sessionId": sessionID,
	})
}

// Shutdown stops the ACP agent subprocess.
func (p *Provider) Shutdown(ctx context.Context) error {
	p.setStatus(agent.ProviderStatus{State: "stopped"})
	if p.proc != nil {
		return p.proc.Close()
	}
	return nil
}

// ── Raw JSON-RPC transport ───────────────────────────────────────

// sendRequest sends a synchronous JSON-RPC request (reads response directly).
// Used only during initialization before the receive loop starts.
func (p *Provider) sendRequest(method string, params interface{}) (interface{}, error) {
	id := p.nextID.Add(1)
	req := map[string]interface{}{
		"jsonrpc": "2.0",
		"id":      id,
		"method":  method,
		"params":  params,
	}
	data, _ := json.Marshal(req)
	if p.cfg.Debug {
		slog.Debug("ACP wire →", "data", truncate(string(data), 500))
	}
	if _, err := p.writer.Write(append(data, '\n')); err != nil {
		return nil, err
	}

	// Read response synchronously
	if !p.scanner.Scan() {
		return nil, fmt.Errorf("connection closed")
	}
	line := p.scanner.Bytes()
	if p.cfg.Debug {
		slog.Debug("ACP wire ←", "data", truncate(string(line), 500))
	}

	var resp map[string]interface{}
	if err := json.Unmarshal(line, &resp); err != nil {
		return nil, fmt.Errorf("parse response: %w", err)
	}
	if errObj, ok := resp["error"]; ok {
		return nil, fmt.Errorf("agent error: %v", errObj)
	}
	return resp["result"], nil
}

// sendRequestAsync sends a JSON-RPC request via the write pipe and waits
// for the matching response on the receive loop.
func (p *Provider) sendRequestAsync(method string, params interface{}) (interface{}, error) {
	id := p.nextID.Add(1)
	ch := make(chan json.RawMessage, 1)
	p.pending.Store(id, ch)
	defer p.pending.Delete(id)

	req := map[string]interface{}{
		"jsonrpc": "2.0",
		"id":      id,
		"method":  method,
		"params":  params,
	}
	data, _ := json.Marshal(req)
	if p.cfg.Debug {
		slog.Debug("ACP wire →", "data", truncate(string(data), 500))
	}
	if _, err := p.writer.Write(append(data, '\n')); err != nil {
		return nil, err
	}

	// Wait for response
	raw := <-ch

	var resp map[string]interface{}
	if err := json.Unmarshal(raw, &resp); err != nil {
		return nil, err
	}
	if errObj, ok := resp["error"]; ok {
		return nil, fmt.Errorf("agent error: %v", errObj)
	}
	return resp["result"], nil
}

func (p *Provider) sendNotification(method string, params interface{}) error {
	notif := map[string]interface{}{
		"jsonrpc": "2.0",
		"method":  method,
		"params":  params,
	}
	data, _ := json.Marshal(notif)
	_, err := p.writer.Write(append(data, '\n'))
	return err
}

// receiveLoop reads JSON-RPC messages from the agent and dispatches them.
func (p *Provider) receiveLoop() {
	for p.scanner.Scan() {
		line := p.scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		if p.cfg.Debug {
			slog.Debug("ACP wire ←", "data", truncate(string(line), 500))
		}

		var msg map[string]json.RawMessage
		if err := json.Unmarshal(line, &msg); err != nil {
			continue
		}

		// Check if this is a response (has "id" and "result" or "error") or
		// an incoming client-side request (has "id" and "method").
		if idRaw, ok := msg["id"]; ok {
			if _, hasResult := msg["result"]; hasResult {
				var id int64
				json.Unmarshal(idRaw, &id)
				if ch, ok := p.pending.Load(id); ok {
					ch.(chan json.RawMessage) <- json.RawMessage(line)
					continue
				}
			}
			if _, hasError := msg["error"]; hasError {
				var id int64
				json.Unmarshal(idRaw, &id)
				if ch, ok := p.pending.Load(id); ok {
					ch.(chan json.RawMessage) <- json.RawMessage(line)
					continue
				}
			}
			if _, hasMethod := msg["method"]; hasMethod {
				p.handleClientRequest(idRaw, msg)
				continue
			}
		}

		// It's a notification — route it
		var methodName string
		if m, ok := msg["method"]; ok {
			json.Unmarshal(m, &methodName)
		}

		if methodName == "session/update" {
			p.routeSessionUpdate(msg["params"])
		}
	}
}

func (p *Provider) routeSessionUpdate(paramsRaw json.RawMessage) {
	var params map[string]json.RawMessage
	if err := json.Unmarshal(paramsRaw, &params); err != nil {
		return
	}

	var update map[string]json.RawMessage
	if u, ok := params["update"]; ok {
		_ = json.Unmarshal(u, &update)
	}
	if update == nil {
		return
	}

	var updateMap map[string]interface{}
	if u, ok := params["update"]; ok {
		_ = json.Unmarshal(u, &updateMap)
	}
	if updateMap == nil {
		updateMap = map[string]interface{}{}
	}

	var kind string
	if k, ok := update["sessionUpdate"]; ok {
		_ = json.Unmarshal(k, &kind)
	}
	if kind == "" {
		kind = stringFromRaw(update["type"])
	}

	p.applySessionUpdateMetadata(updateMap)
	p.events <- agent.Event{Type: "session_update", Data: safeSessionUpdateEvent(kind, updateMap)}

	switch kind {
	case "agent_message_chunk":
		if content, ok := update["content"]; ok {
			var cb map[string]interface{}
			_ = json.Unmarshal(content, &cb)
			// Content block is {"type": "text", "text": "Hello"}
			if t, ok := cb["text"].(string); ok && t != "" {
				p.draftMu.Lock()
				p.draftText.WriteString(t)
				p.draftMu.Unlock()
				p.events <- agent.Event{Type: "draft", Data: map[string]string{"text": t}}
			}
		}
	case "agent_thought_chunk":
		if content, ok := update["content"]; ok {
			var cb map[string]interface{}
			_ = json.Unmarshal(content, &cb)
			if t, ok := cb["text"].(string); ok && t != "" {
				p.events <- agent.Event{Type: "thought", Data: map[string]string{"text": t}}
			}
		}
	case "tool_call":
		p.events <- agent.Event{Type: "status", Data: map[string]interface{}{"type": "tool_call", "title": stringFromRaw(update["title"])}}
	case "tool_call_update":
		p.events <- agent.Event{Type: "status", Data: map[string]interface{}{"type": "tool_status", "title": stringFromRaw(update["title"]), "status": stringFromRaw(update["status"])}}
	case "plan":
		p.events <- agent.Event{Type: "plan", Data: safeSessionUpdateEvent(kind, updateMap)}
	}
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "..."
}

// Unused import suppression
var _ = bytes.Contains

// CollectedDraft returns the accumulated draft text from the last prompt turn.
func (p *Provider) CollectedDraft() string {
	p.draftMu.Lock()
	defer p.draftMu.Unlock()
	return p.draftText.String()
}
