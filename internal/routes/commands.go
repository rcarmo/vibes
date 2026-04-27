package routes

import (
	"net/http"

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
		return "Model switching not yet implemented in Go port.", true
	case startsWith(msg, "/thinking"):
		return "Thinking level control not yet implemented in Go port.", true
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

	// Execute with timeout (implemented in a future iteration with os/exec)
	return "Shell command execution not yet implemented in Go port: `" + cmd + "`"
}
