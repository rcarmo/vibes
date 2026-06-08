// Package pi implements the Pi native RPC provider for Vibes.
//
// Pi's `--mode rpc` protocol uses newline-delimited JSON over stdio.
// This provides richer features than ACP: streaming drafts, thinking traces,
// tool execution events, live model/thinking control, and mid-turn steering.
package pi

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"

	"github.com/rcarmo/vibes/internal/agent"
)

// Config configures a Pi RPC provider.
type Config struct {
	Command string   // pi binary path
	Args    []string // arguments (e.g., ["--mode", "rpc", "--no-session"])
	WorkDir string   // working directory
}

// Provider implements agent.Provider for Pi's native RPC protocol.
type Provider struct {
	cfg    Config
	cmd    *exec.Cmd
	stdin  io.WriteCloser
	stdout io.Reader
	events chan agent.Event

	mu     sync.RWMutex
	status agent.ProviderStatus
	cancel context.CancelFunc
	nextID atomic.Int64
}

// New creates a new Pi RPC provider.
func New(cfg Config) *Provider {
	return &Provider{
		cfg:    cfg,
		events: make(chan agent.Event, 256),
		status: agent.ProviderStatus{State: "stopped"},
	}
}

func (p *Provider) ID() string                 { return "pi" }
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

func (p *Provider) updateStatus(mut func(*agent.ProviderStatus)) {
	p.mu.Lock()
	defer p.mu.Unlock()
	mut(&p.status)
}

func (p *Provider) requestID() string {
	return strconv.FormatInt(p.nextID.Add(1), 10)
}

// Initialize spawns the Pi subprocess and waits for readiness.
func (p *Provider) Initialize(ctx context.Context) error {
	args := append([]string{"--mode", "rpc", "--no-session"}, p.cfg.Args...)

	slog.Info("spawning Pi RPC agent",
		"command", p.cfg.Command,
		"args", strings.Join(args, " "),
	)

	cmd := exec.CommandContext(ctx, p.cfg.Command, args...)
	if p.cfg.WorkDir != "" {
		cmd.Dir = p.cfg.WorkDir
	}

	stdin, err := cmd.StdinPipe()
	if err != nil {
		return fmt.Errorf("pi stdin: %w", err)
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return fmt.Errorf("pi stdout: %w", err)
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return fmt.Errorf("pi stderr: %w", err)
	}

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("pi start: %w", err)
	}

	p.cmd = cmd
	p.stdin = stdin
	p.stdout = stdout

	// Start stream readers
	go p.readEvents()
	go p.readStderr(stderr)

	p.setStatus(agent.ProviderStatus{State: "idle", Model: "pi"})
	slog.Info("Pi RPC agent started", "pid", cmd.Process.Pid)
	return nil
}

// Prompt sends a user message via Pi RPC.
func (p *Provider) Prompt(ctx context.Context, message string, threadID int64) error {
	if p.stdin == nil {
		return fmt.Errorf("Pi RPC agent is not initialized")
	}

	p.updateStatus(func(s *agent.ProviderStatus) {
		s.State = "busy"
	})

	cmd := map[string]interface{}{
		"id":      p.requestID(),
		"type":    "prompt",
		"message": message,
	}
	return p.send(cmd)
}

// Cancel aborts the current Pi request.
func (p *Provider) Cancel() error {
	return p.send(map[string]string{"id": p.requestID(), "type": "abort"})
}

// Shutdown stops the Pi subprocess.
func (p *Provider) Shutdown(ctx context.Context) error {
	p.setStatus(agent.ProviderStatus{State: "stopped"})
	if p.stdin != nil {
		p.stdin.Close()
	}
	if p.cmd != nil && p.cmd.Process != nil {
		p.cmd.Process.Kill()
		p.cmd.Wait()
	}
	return nil
}

// send writes a JSON command to Pi's stdin.
func (p *Provider) send(cmd interface{}) error {
	data, err := json.Marshal(cmd)
	if err != nil {
		return err
	}
	data = append(data, '\n')
	_, err = p.stdin.Write(data)
	return err
}

// readEvents reads NDJSON events from Pi's stdout and routes them.
func (p *Provider) readEvents() {
	scanner := bufio.NewScanner(p.stdout)
	// Pi events can occasionally include large payloads (tool output / blocks),
	// so keep a larger scanner ceiling to avoid silent token-too-long exits.
	scanner.Buffer(make([]byte, 1<<20), 16<<20) // 16 MB max token

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		var event map[string]interface{}
		if err := json.Unmarshal(line, &event); err != nil {
			slog.Debug("Pi event decode failed", "error", err)
			continue
		}

		p.routeEvent(event)
	}

	if err := scanner.Err(); err != nil {
		slog.Warn("Pi event stream terminated", "error", err)
		p.events <- agent.Event{Type: "status", Data: map[string]string{"state": "error", "error": err.Error()}}
	}
}

func (p *Provider) readStderr(stderr io.Reader) {
	scanner := bufio.NewScanner(stderr)
	scanner.Buffer(make([]byte, 64<<10), 1<<20) // 1 MB line limit
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		slog.Debug("Pi stderr", "line", line)
	}
	if err := scanner.Err(); err != nil {
		slog.Debug("Pi stderr stream terminated", "error", err)
	}
}

// routeEvent classifies a Pi event and sends it to the events channel.
func (p *Provider) routeEvent(event map[string]interface{}) {
	eventType, _ := event["type"].(string)

	switch eventType {
	case "response":
		p.routeResponse(event)

	case "agent_start":
		p.updateStatus(func(s *agent.ProviderStatus) { s.State = "busy" })
		p.events <- agent.Event{Type: "status", Data: map[string]string{"state": "active"}}

	case "agent_end":
		p.updateStatus(func(s *agent.ProviderStatus) { s.State = "idle" })
		p.events <- agent.Event{Type: "response", Data: event}

	case "message_start", "message_update", "message_end":
		p.routeMessageEvent(event)

	case "tool_call", "tool_result",
		"tool_execution_start", "tool_execution_update", "tool_execution_end",
		"turn_start", "turn_end", "queue_update", "auto_retry_start", "auto_retry_end", "session":
		p.events <- agent.Event{Type: "status", Data: event}

	case "extension_ui_request":
		p.events <- agent.Event{Type: "permission", Data: event}

	case "error", "backend_exited":
		p.updateStatus(func(s *agent.ProviderStatus) { s.State = "error" })
		p.events <- agent.Event{Type: "error", Data: event}

	default:
		// Unknown events are still useful for diagnostics and future Pi protocol additions.
		p.events <- agent.Event{Type: "status", Data: event}
	}
}

func (p *Provider) routeMessageEvent(event map[string]interface{}) {
	payload, _ := event["assistantMessageEvent"].(map[string]interface{})
	if payload == nil {
		return
	}

	deltaType, _ := payload["type"].(string)
	text := firstString(payload, "delta", "content")
	switch deltaType {
	case "text_delta":
		if text != "" {
			p.events <- agent.Event{Type: "draft", Data: map[string]string{"text": text}}
		}
	case "thinking_delta":
		if text != "" {
			p.events <- agent.Event{Type: "thought", Data: map[string]string{"text": text}}
		}
	}
}

func (p *Provider) routeResponse(event map[string]interface{}) {
	if success, ok := event["success"].(bool); ok && !success {
		p.updateStatus(func(s *agent.ProviderStatus) { s.State = "error" })
		p.events <- agent.Event{Type: "error", Data: event}
		return
	}

	command, _ := event["command"].(string)
	switch command {
	case "set_model":
		if data, ok := event["data"].(map[string]interface{}); ok {
			provider, _ := data["provider"].(string)
			modelID, _ := data["id"].(string)
			model := strings.Trim(strings.Trim(provider+"/"+modelID, "/"), " ")
			if model != "" {
				p.updateStatus(func(s *agent.ProviderStatus) { s.Model = model })
			}
		}
	case "get_state":
		p.updateStatusFromState(event["data"])
	}

	p.events <- agent.Event{Type: "status", Data: event}
}

func (p *Provider) updateStatusFromState(data interface{}) {
	state, ok := data.(map[string]interface{})
	if !ok {
		return
	}
	p.updateStatus(func(s *agent.ProviderStatus) {
		if model, ok := state["model"].(map[string]interface{}); ok {
			provider, _ := model["provider"].(string)
			modelID, _ := model["id"].(string)
			label := strings.Trim(strings.Trim(provider+"/"+modelID, "/"), " ")
			if label != "" {
				s.Model = label
			}
		}
		if pct, ok := numericContextPct(state); ok {
			s.ContextPct = pct
		}
	})
}

func firstString(m map[string]interface{}, keys ...string) string {
	for _, key := range keys {
		if value, ok := m[key].(string); ok {
			return value
		}
	}
	return ""
}

func numericContextPct(state map[string]interface{}) (float64, bool) {
	for _, key := range []string{"contextPct", "contextPercent", "contextPercentage"} {
		if value, ok := state[key].(float64); ok {
			if value > 1 {
				value /= 100
			}
			return value, true
		}
	}
	if context, ok := state["context"].(map[string]interface{}); ok {
		for _, key := range []string{"pct", "percent", "percentage", "usage"} {
			if value, ok := context[key].(float64); ok {
				if value > 1 {
					value /= 100
				}
				return value, true
			}
		}
	}
	return 0, false
}

// Steer sends a mid-turn steering message.
func (p *Provider) Steer(message string) error {
	return p.send(map[string]string{"id": p.requestID(), "type": "steer", "message": message})
}

// SetModel changes the model live.
func (p *Provider) SetModel(provider, modelID string) error {
	return p.send(map[string]interface{}{
		"id":       p.requestID(),
		"type":     "set_model",
		"provider": provider,
		"modelId":  modelID,
	})
}

// SetThinkingLevel changes the thinking level live.
func (p *Provider) SetThinkingLevel(level string) error {
	return p.send(map[string]interface{}{
		"id":    p.requestID(),
		"type":  "set_thinking_level",
		"level": level,
	})
}

// NewSession resets the Pi session.
func (p *Provider) NewSession() error {
	return p.send(map[string]string{"id": p.requestID(), "type": "new_session"})
}
