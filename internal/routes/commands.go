package routes

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/db"
)

var (
	githubAPIBaseURL = "https://api.github.com"
	githubHTTPClient = &http.Client{Timeout: 10 * time.Second}
)

// SlashCommand defines a slash command available to the frontend.
type SlashCommand struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Category    string `json:"category,omitempty"`
}

// SlashCommandEnv provides dependencies for local slash command handling.
type SlashCommandEnv struct {
	Registry  *agent.Registry
	DB        *db.DB
	BackendID string
}

// SlashCommandResult describes the outcome of a locally handled command.
type SlashCommandResult struct {
	Action               string `json:"action,omitempty"`
	Message              string `json:"message,omitempty"`
	ModelLabel           string `json:"model_label,omitempty"`
	ThinkingLevel        string `json:"thinking_level,omitempty"`
	SupportsThinking     bool   `json:"supports_thinking,omitempty"`
	UserName             string `json:"user_name,omitempty"`
	UserAvatar           string `json:"user_avatar,omitempty"`
	UserAvatarBackground string `json:"user_avatar_background,omitempty"`
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
		{Name: "/user-name", Description: "Show or set your display name", Category: "profile"},
		{Name: "/user-avatar", Description: "Show or set your avatar URL", Category: "profile"},
		{Name: "/user-github", Description: "Set name/avatar from GitHub profile", Category: "profile"},
		{Name: "/commands", Description: "List all slash commands", Category: "system"},
		{Name: "/clear", Description: "Clear the timeline display", Category: "system"},
		{Name: "/shell", Description: "Run a shell command (30s timeout)", Category: "tools"},
		{Name: "/bash", Description: "Alias for /shell", Category: "tools"},
	}
}

// GetCommands returns the handler for listing slash commands.
func GetCommands() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		jsonResp(w, builtinCommands())
	}
}

// HandleSlashCommand processes a slash command and returns a structured result.
// Returns true if the message was a slash command (handled), false otherwise.
func HandleSlashCommand(msg string, env SlashCommandEnv) (*SlashCommandResult, bool) {
	if len(msg) == 0 || msg[0] != '/' {
		return nil, false
	}

	registry := env.Registry
	backendID := strings.TrimSpace(env.BackendID)
	if backendID == "" {
		backendID = "default"
	}
	getProvider := func() (agent.Provider, error) {
		if registry == nil {
			return nil, fmt.Errorf("no active agent")
		}
		return registry.Get(backendID)
	}
	result := &SlashCommandResult{}

	switch {
	case msg == "/commands":
		result.Message = formatCommands()
		return result, true

	case msg == "/abort":
		if p, err := getProvider(); err == nil {
			_ = p.Cancel()
		}
		result.Message = "Request cancelled."
		return result, true

	case startsWith(msg, "/model list"):
		result.Message = "Model listing not yet implemented in Go port."
		return result, true

	case startsWith(msg, "/model"):
		arg := strings.TrimSpace(msg[6:])
		p, err := getProvider()
		if err != nil {
			result.Message = "No active agent."
			return result, true
		}
		if arg == "" {
			result.Message = "Current model: `" + p.Status().Model + "`"
			result.ModelLabel = p.Status().Model
			return result, true
		}
		type modelSetter interface {
			SetModel(provider, modelID string) error
		}
		if ms, ok := p.(modelSetter); ok {
			parts := strings.SplitN(arg, "/", 2)
			if len(parts) == 2 {
				if err := ms.SetModel(parts[0], parts[1]); err != nil {
					result.Message = "Failed to set model: " + err.Error()
					return result, true
				}
				result.Message = "Model set to `" + arg + "`"
				result.ModelLabel = arg
				return result, true
			}
			result.Message = "Usage: /model provider/model-id"
			return result, true
		}
		result.Message = "Model switching requires Pi agent."
		return result, true

	case startsWith(msg, "/thinking"):
		arg := strings.TrimSpace(msg[9:])
		p, err := getProvider()
		if err != nil {
			result.Message = "No active agent."
			return result, true
		}
		type thinkingSetter interface {
			SetThinkingLevel(level string) error
		}
		if ts, ok := p.(thinkingSetter); ok {
			result.SupportsThinking = true
			if arg == "" {
				result.Message = "Usage: /thinking low|medium|high"
				return result, true
			}
			if err := ts.SetThinkingLevel(arg); err != nil {
				result.Message = "Failed to set thinking level: " + err.Error()
				return result, true
			}
			result.Message = "Thinking level set to `" + arg + "`"
			result.ThinkingLevel = arg
			return result, true
		}
		result.Message = "Thinking level control requires Pi agent."
		return result, true

	case msg == "/restart":
		p, err := getProvider()
		if err != nil {
			result.Message = "No active agent."
			return result, true
		}
		type sessionResetter interface {
			NewSession() error
		}
		if sr, ok := p.(sessionResetter); ok {
			if err := sr.NewSession(); err != nil {
				result.Message = "Failed to restart session: " + err.Error()
				return result, true
			}
			result.Message = "Session restarted."
			return result, true
		}
		result.Message = "Session restart not yet implemented in Go port."
		return result, true

	case startsWith(msg, "/steer"):
		arg := strings.TrimSpace(msg[6:])
		if arg == "" {
			result.Message = "Usage: /steer <message>"
			return result, true
		}
		p, err := getProvider()
		if err != nil {
			result.Message = "No active agent."
			return result, true
		}
		type steerer interface {
			Steer(message string) error
		}
		if s, ok := p.(steerer); ok {
			if err := s.Steer(arg); err != nil {
				result.Message = "Failed to steer active turn: " + err.Error()
				return result, true
			}
			result.Message = "Steering message sent."
			return result, true
		}
		result.Message = "Steering requires Pi agent."
		return result, true

	case startsWith(msg, "/user-name"):
		if env.DB == nil {
			result.Message = "Profile storage is unavailable."
			return result, true
		}
		arg := strings.TrimSpace(msg[len("/user-name"):])
		profile, err := env.DB.GetUserProfile()
		if err != nil {
			result.Message = "Failed to load user profile: " + err.Error()
			return result, true
		}
		if arg == "" {
			result.Message = "Current user name: `" + profile.Name + "`"
			result.UserName = profile.Name
			result.UserAvatar = profile.AvatarURL
			result.UserAvatarBackground = profile.AvatarBackground
			return result, true
		}
		profile.Name = arg
		if err := env.DB.SetUserProfile(profile); err != nil {
			result.Message = "Failed to save user profile: " + err.Error()
			return result, true
		}
		result.Message = "User name updated to `" + profile.Name + "`."
		result.UserName = profile.Name
		result.UserAvatar = profile.AvatarURL
		result.UserAvatarBackground = profile.AvatarBackground
		return result, true

	case startsWith(msg, "/user-avatar"):
		if env.DB == nil {
			result.Message = "Profile storage is unavailable."
			return result, true
		}
		arg := strings.TrimSpace(msg[len("/user-avatar"):])
		profile, err := env.DB.GetUserProfile()
		if err != nil {
			result.Message = "Failed to load user profile: " + err.Error()
			return result, true
		}
		if arg == "" {
			current := profile.AvatarURL
			if current == "" {
				current = "(not set)"
			}
			result.Message = "Current user avatar: `" + current + "`"
			result.UserName = profile.Name
			result.UserAvatar = profile.AvatarURL
			result.UserAvatarBackground = profile.AvatarBackground
			return result, true
		}
		profile.AvatarURL = arg
		if err := env.DB.SetUserProfile(profile); err != nil {
			result.Message = "Failed to save user profile: " + err.Error()
			return result, true
		}
		result.Message = "User avatar updated."
		result.UserName = profile.Name
		result.UserAvatar = profile.AvatarURL
		result.UserAvatarBackground = profile.AvatarBackground
		return result, true

	case startsWith(msg, "/user-github"):
		if env.DB == nil {
			result.Message = "Profile storage is unavailable."
			return result, true
		}
		username := strings.TrimSpace(msg[len("/user-github"):])
		if username == "" {
			result.Message = "Usage: /user-github <username>"
			return result, true
		}
		gh, err := fetchGitHubProfile(username)
		if err != nil {
			result.Message = "Failed to fetch GitHub profile: " + err.Error()
			return result, true
		}
		profile := db.UserProfile{
			Name:             gh.Name,
			AvatarURL:        gh.AvatarURL,
			AvatarBackground: "",
		}
		if profile.Name == "" {
			profile.Name = gh.Login
		}
		if err := env.DB.SetUserProfile(profile); err != nil {
			result.Message = "Failed to save user profile: " + err.Error()
			return result, true
		}
		result.Message = fmt.Sprintf("Updated user profile from GitHub `@%s`.", gh.Login)
		result.UserName = profile.Name
		result.UserAvatar = profile.AvatarURL
		result.UserAvatarBackground = profile.AvatarBackground
		return result, true

	case msg == "/clear":
		result.Action = "clear"
		return result, true

	case startsWith(msg, "/shell"):
		result.Message = executeShellCommand(msg[6:])
		return result, true

	case startsWith(msg, "/bash"):
		result.Message = executeShellCommand(msg[5:])
		return result, true
	}

	return nil, false
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

type gitHubProfile struct {
	Login     string `json:"login"`
	Name      string `json:"name"`
	AvatarURL string `json:"avatar_url"`
	Message   string `json:"message"`
}

func fetchGitHubProfile(username string) (*gitHubProfile, error) {
	username = strings.TrimSpace(username)
	if username == "" {
		return nil, fmt.Errorf("missing username")
	}
	endpoint := strings.TrimRight(githubAPIBaseURL, "/") + "/users/" + url.PathEscape(username)
	req, err := http.NewRequest(http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("User-Agent", "vibes")

	resp, err := githubHTTPClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var profile gitHubProfile
	if err := json.NewDecoder(resp.Body).Decode(&profile); err != nil {
		return nil, err
	}
	if resp.StatusCode == http.StatusNotFound {
		return nil, fmt.Errorf("GitHub user %q not found", username)
	}
	if resp.StatusCode >= 400 {
		msg := strings.TrimSpace(profile.Message)
		if msg == "" {
			msg = resp.Status
		}
		return nil, fmt.Errorf("GitHub API error: %s", msg)
	}
	if strings.TrimSpace(profile.Login) == "" {
		return nil, fmt.Errorf("invalid GitHub profile response")
	}
	profile.Name = strings.TrimSpace(profile.Name)
	profile.AvatarURL = strings.TrimSpace(profile.AvatarURL)
	return &profile, nil
}
