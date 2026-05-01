package routes

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/db"
	"github.com/rcarmo/vibes/internal/server/sse"
)

// ActionDef defines a custom action from config/endpoints.json.
type ActionDef struct {
	Description string   `json:"description"`
	Prompt      string   `json:"prompt"`
	Params      []string `json:"params"`
	AgentID     string   `json:"agent_id"`
}

// ActionsConfig is the top-level config/endpoints.json structure.
type ActionsConfig struct {
	Endpoints map[string]ActionDef `json:"endpoints"`
}

// LoadActions reads and parses the custom endpoints config file.
func LoadActions(path string) (*ActionsConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return &ActionsConfig{Endpoints: map[string]ActionDef{}}, nil
		}
		return nil, err
	}
	var cfg ActionsConfig
	if err := json.Unmarshal(data, &cfg); err != nil {
		return nil, err
	}
	if cfg.Endpoints == nil {
		cfg.Endpoints = map[string]ActionDef{}
	}
	slog.Info("loaded custom actions", "count", len(cfg.Endpoints))
	return &cfg, nil
}

// Actions mounts the custom action route. (fixes #3)
func Actions(actions *ActionsConfig, registry *agent.Registry, database *db.DB, broker *sse.Broker) func(r chi.Router) {
	return func(r chi.Router) {
		r.Post("/{agent_id}/action/{action_id}", triggerAction(actions, registry, database, broker))
	}
}

func triggerAction(actions *ActionsConfig, registry *agent.Registry, database *db.DB, broker *sse.Broker) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		agentID := chi.URLParam(r, "agent_id")
		actionID := chi.URLParam(r, "action_id")

		action, ok := actions.Endpoints[actionID]
		if !ok {
			jsonError(w, "unknown action: "+actionID, http.StatusNotFound)
			return
		}

		var req struct {
			ThreadID *int64                 `json:"thread_id"`
			Params   map[string]interface{} `json:"params"`
		}
		decodeJSON(r, &req) // params are optional

		// Build prompt from action definition
		prompt := action.Prompt
		if prompt == "" {
			prompt = action.Description
		}
		if prompt == "" {
			prompt = actionID
		}

		// Append params if provided
		if len(req.Params) > 0 {
			paramsJSON, _ := json.Marshal(req.Params)
			prompt += "\n\nParams: " + string(paramsJSON)
		}

		// Validate agent
		provider, err := registry.Get(agentID)
		if err != nil {
			jsonError(w, "unknown agent: "+agentID, http.StatusBadRequest)
			return
		}

		// Store the action trigger as a user message
		data, _ := db.MarshalInteraction(db.InteractionData{
			Type:     "user_message",
			Content:  prompt,
			ThreadID: req.ThreadID,
		})
		postID, err := database.InsertInteraction(data)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		threadID := postID
		if req.ThreadID != nil {
			threadID = *req.ThreadID
		}

		// Send to agent asynchronously
		go func() {
			provider.Prompt(r.Context(), prompt, threadID)
		}()

		w.WriteHeader(http.StatusAccepted)
		jsonResp(w, map[string]interface{}{
			"status":    "queued",
			"agent_id":  agentID,
			"action_id": actionID,
		})
	}
}
