package routes

import (
	"net/http"
	"strings"
	"time"

	"github.com/rcarmo/vibes/internal/agent"
)

// SlashCommand defines a slash command available to the frontend.
type SlashCommand struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Category    string `json:"category,omitempty"`
}

// builtinCommands returns the list of available slash commands.
func builtinCommands() []SlashCommand {
	return []SlashCommand{
		{Name: "/model", Description: "Show or change the active model", Category: "agent"},
		{Name: "/model list", Description: "List available models", Category: "agent"},
		{Name: "/thinking", Description: "Show or change thinking level", Category: "agent"},
		{Name: "/restart", Description: "Reset agent session", Category: "agent"},
		{Name: "/abort", Description: "Cancel current request", Category: "agent"},
		{Name: "/steer", Description: "Send mid-turn steering guidance", Category: "agent"},
		{Name: "/commands", Description: "List all slash commands", Category: "system"},
		{Name: "/clear", Description: "Clear the timeline display", Category: "system"},
		{Name: "/shell", Description: "Run a shell command (30s timeout)", Category: "tools"},
	}
}

// GetCommands returns the handler for listing slash commands.
func GetCommands() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		jsonResp(w, builtinCommands())
	}
}

// HandleSlashCommand processes a slash command and returns a response or error.
// Returns true if the message was a slash command (handled), false otherwise.
func HandleSlashCommand(msg string, registry *agent.Registry) (string, bool) {
	if len(msg) == 0 || msg[0] != '/' {
		return "", false
	}

	switch {
	case msg == "/commands":
		return formatCommands(), true
	case msg == "/abort":
		p, err := registry.Get("default")
		if err == nil {
			p.Cancel()
		}
		return "Request cancelled.", true
	case startsWith(msg, "/model list"):
		return "Model listing not yet implemented in Go port.", true
	case startsWith(msg, "/model"):
		arg := strings.TrimSpace(msg[6:])
		if arg == "" {
			p, err := registry.Get("default")
			if err == nil {
				return "Current model: `" + p.Status().Model + "`", true
			}
			return "No active agent.", true
		}
		// Try to set model (Pi only)
		p, err := registry.Get("default")
		if err != nil {
			return "No active agent.", true
		}
		type modelSetter interface {
			SetModel(provider, modelID string) error
		}
		if ms, ok := p.(modelSetter); ok {
			parts := strings.SplitN(arg, "/", 2)
			if len(parts) == 2 {
				ms.SetModel(parts[0], parts[1])
				return "Model set to `" + arg + "`", true
			}
			return "Usage: /model provider/model-id", true
		}
		return "Model switching requires Pi agent.", true
	case startsWith(msg, "/thinking"):
		arg := strings.TrimSpace(msg[9:])
		if arg == "" {
			return "Usage: /thinking low|medium|high", true
		}
		p, err := registry.Get("default")
		if err != nil {
			return "No active agent.", true
		}
		type thinkingSetter interface {
			SetThinkingLevel(level string) error
		}
		if ts, ok := p.(thinkingSetter); ok {
			ts.SetThinkingLevel(arg)
			return "Thinking level set to `" + arg + "`", true
		}
		return "Thinking level control requires Pi agent.", true
	case msg == "/restart":
		return "Session restart not yet implemented in Go port.", true
	case startsWith(msg, "/steer"):
		return "Steering not yet implemented in Go port.", true
	case msg == "/clear":
		return "[clear]", true
	case startsWith(msg, "/shell"):
		return executeShellCommand(msg[6:]), true
	}

	return "", false
}

func formatCommands() string {
	cmds := builtinCommands()
	result := "**Available commands:**\n\n"
	for _, cmd := range cmds {
		result += "- `" + cmd.Name + "` — " + cmd.Description + "\n"
	}
	return result
}

func startsWith(s, prefix string) bool {
	return len(s) >= len(prefix) && s[:len(prefix)] == prefix
}

func executeShellCommand(cmd string) string {
	// Trim leading space
	for len(cmd) > 0 && cmd[0] == ' ' {
		cmd = cmd[1:]
	}
	if cmd == "" {
		return "Usage: /shell <command>"
	}

	out, _ := ExecuteShell(cmd, 30*time.Second)
	if out == "" {
		return "(no output)"
	}
	return "```\n" + out + "```"
}
