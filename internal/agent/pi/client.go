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
	"strings"
	"sync"

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
	cmd.Stderr = nil // discard stderr

	if err := cmd.Start(); err != nil {
		return fmt.Errorf("pi start: %w", err)
	}

	p.cmd = cmd
	p.stdin = stdin
	p.stdout = stdout

	// Start event reader
	go p.readEvents()

	p.setStatus(agent.ProviderStatus{State: "idle", Model: "pi"})
	slog.Info("Pi RPC agent started", "pid", cmd.Process.Pid)
	return nil
}

// Prompt sends a user message via Pi RPC.
func (p *Provider) Prompt(ctx context.Context, message string, threadID int64) error {
	p.setStatus(agent.ProviderStatus{State: "busy", Model: p.status.Model})
	defer p.setStatus(agent.ProviderStatus{State: "idle", Model: p.status.Model})

	cmd := map[string]interface{}{
		"type":    "prompt",
		"message": message,
	}
	return p.send(cmd)
}

// Cancel aborts the current Pi request.
func (p *Provider) Cancel() error {
	return p.send(map[string]string{"type": "abort"})
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
	scanner.Buffer(make([]byte, 1<<20), 1<<20) // 1 MB buffer

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		var event map[string]interface{}
		if err := json.Unmarshal(line, &event); err != nil {
			continue
		}

		p.routeEvent(event)
	}
}

// routeEvent classifies a Pi event and sends it to the events channel.
func (p *Provider) routeEvent(event map[string]interface{}) {
	eventType, _ := event["type"].(string)

	switch eventType {
	case "response":
		// Acknowledgement — ignore

	case "agent_start":
		p.events <- agent.Event{Type: "status", Data: map[string]string{"state": "active"}}

	case "agent_end":
		p.events <- agent.Event{Type: "response", Data: event}

	case "message_start", "message_update", "message_end":
		// Check for delta type
		if delta, ok := event["delta"].(map[string]interface{}); ok {
			deltaType, _ := delta["type"].(string)
			switch deltaType {
			case "text_delta":
				text, _ := delta["text"].(string)
				p.events <- agent.Event{Type: "draft", Data: map[string]string{"text": text}}
			case "thinking_delta":
				text, _ := delta["text"].(string)
				p.events <- agent.Event{Type: "thought", Data: map[string]string{"text": text}}
			}
		}

	case "tool_execution_start":
		p.events <- agent.Event{Type: "status", Data: event}

	case "tool_execution_update":
		p.events <- agent.Event{Type: "status", Data: event}

	case "tool_execution_end":
		p.events <- agent.Event{Type: "status", Data: event}

	case "turn_start", "turn_end":
		p.events <- agent.Event{Type: "status", Data: event}

	case "extension_ui_request":
		p.events <- agent.Event{Type: "permission", Data: event}

	default:
		// Unknown events forwarded as status
		p.events <- agent.Event{Type: "status", Data: event}
	}
}

// Steer sends a mid-turn steering message.
func (p *Provider) Steer(message string) error {
	return p.send(map[string]string{"type": "steer", "message": message})
}

// SetModel changes the model live.
func (p *Provider) SetModel(provider, modelID string) error {
	return p.send(map[string]interface{}{
		"type":     "set_model",
		"provider": provider,
		"modelId":  modelID,
	})
}

// SetThinkingLevel changes the thinking level live.
func (p *Provider) SetThinkingLevel(level string) error {
	return p.send(map[string]interface{}{
		"type":  "set_thinking_level",
		"level": level,
	})
}

// NewSession resets the Pi session.
func (p *Provider) NewSession() error {
	return p.send(map[string]string{"type": "new_session"})
}
