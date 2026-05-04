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
	ID      string
	Command string
	Args    []string
	WorkDir string
	Env     map[string]string
	Debug   bool
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
	pending   sync.Map // id → chan json.RawMessage

	mu     sync.RWMutex
	status agent.ProviderStatus
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
		"clientCapabilities": map[string]interface{}{},
	})
	if err != nil {
		proc.Close()
		return fmt.Errorf("initialize: %w", err)
	}

	model := ""
	if result, ok := initResult.(map[string]interface{}); ok {
		if ai, ok := result["agentInfo"].(map[string]interface{}); ok {
			model, _ = ai["name"].(string)
		}
	}

	// Start receive loop (must be after init since init reads synchronously)
	go p.receiveLoop()

	// Create session
	cwd := p.cfg.WorkDir
	if cwd == "" {
		cwd, _ = os.Getwd()
	}
	sessResult, err := p.sendRequestAsync("session/new", map[string]interface{}{
		"cwd":        cwd,
		"mcpServers": []interface{}{},
	})
	if err != nil {
		slog.Warn("new_session failed (agent may need auth)", "id", p.cfg.ID, "error", err)
	} else if result, ok := sessResult.(map[string]interface{}); ok {
		if sid, ok := result["sessionId"].(string); ok {
			p.sessionID = sid
		}
	}

	p.setStatus(agent.ProviderStatus{State: "idle", Model: model})
	slog.Info("ACP agent initialized", "id", p.cfg.ID, "agent", model, "session", p.sessionID)
	return nil
}

// Prompt sends a user message to the ACP agent.
func (p *Provider) Prompt(ctx context.Context, message string, threadID int64) error {
	if p.writer == nil {
		return fmt.Errorf("ACP agent %s is not initialized", p.cfg.ID)
	}
	p.setStatus(agent.ProviderStatus{State: "busy", Model: p.status.Model})
	defer p.setStatus(agent.ProviderStatus{State: "idle", Model: p.status.Model})

	params := map[string]interface{}{
		"prompt": []interface{}{
			map[string]interface{}{"type": "text", "text": message},
		},
	}
	if p.sessionID != "" {
		params["sessionId"] = p.sessionID
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
	if p.sessionID == "" {
		return nil
	}
	return p.sendNotification("session/cancel", map[string]interface{}{
		"sessionId": p.sessionID,
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

		// Check if this is a response (has "id" and "result" or "error")
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
		json.Unmarshal(u, &update)
	}
	if update == nil {
		return
	}

	var kind string
	if k, ok := update["sessionUpdate"]; ok {
		json.Unmarshal(k, &kind)
	}

	switch kind {
	case "agent_message_chunk":
		// Extract text from the content block
		if content, ok := update["content"]; ok {
			var cb map[string]interface{}
			json.Unmarshal(content, &cb)
			if text, ok := cb["text"].(map[string]interface{}); ok {
				if t, ok := text["text"].(string); ok {
					p.events <- agent.Event{Type: "draft", Data: map[string]string{"text": t}}
				}
			}
		}
	case "agent_thought_chunk":
		if content, ok := update["content"]; ok {
			var cb map[string]interface{}
			json.Unmarshal(content, &cb)
			if text, ok := cb["text"].(map[string]interface{}); ok {
				if t, ok := text["text"].(string); ok {
					p.events <- agent.Event{Type: "thought", Data: map[string]string{"text": t}}
				}
			}
		}
	case "tool_call":
		p.events <- agent.Event{Type: "status", Data: string(update["title"])}
	case "tool_call_update":
		p.events <- agent.Event{Type: "status", Data: string(update["status"])}
	case "plan":
		p.events <- agent.Event{Type: "plan", Data: string(paramsRaw)}
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
