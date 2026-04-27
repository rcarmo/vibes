package routes

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/db"
	"github.com/rcarmo/vibes/internal/server/sse"
)

// Agents mounts agent-related routes.
func Agents(registry *agent.Registry, database *db.DB, broker *sse.Broker) func(r chi.Router) {
	return func(r chi.Router) {
		r.Get("/", listAgents(registry))
		r.Get("/status", getAgentStatus(registry))
		r.Post("/{id}/message", sendAgentMessage(registry, database, broker))
		r.Get("/whitelist", getWhitelist(database))
		r.Post("/whitelist", addWhitelist(database))
		r.Delete("/whitelist", removeWhitelist(database))
	}
}

func listAgents(registry *agent.Registry) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ids := registry.List()
		agents := make([]map[string]interface{}, 0, len(ids))
		for _, id := range ids {
			p, _ := registry.Get(id)
			status := p.Status()
			agents = append(agents, map[string]interface{}{
				"id":     id,
				"status": status.State,
				"model":  status.Model,
				"active": id == registry.Active(),
			})
		}
		jsonResp(w, agents)
	}
}

func getAgentStatus(registry *agent.Registry) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		p, err := registry.Get("default")
		if err != nil {
			jsonResp(w, map[string]string{"status": "no_agent"})
			return
		}
		status := p.Status()
		jsonResp(w, map[string]interface{}{
			"status":      status.State,
			"model":       status.Model,
			"context_pct": status.ContextPct,
			"agent_id":    p.ID(),
		})
	}
}

func sendAgentMessage(registry *agent.Registry, database *db.DB, broker *sse.Broker) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		agentID := chi.URLParam(r, "id")

		var req struct {
			Content  string  `json:"content"`
			ThreadID *int64  `json:"thread_id"`
			MediaIDs []int64 `json:"media_ids"`
		}
		if err := decodeJSON(r, &req); err != nil {
			jsonError(w, "invalid body", http.StatusBadRequest)
			return
		}
		if req.Content == "" {
			jsonError(w, "content is required", http.StatusBadRequest)
			return
		}

		// Store the user message
		interaction := db.InteractionData{
			Type:     "user_message",
			Content:  req.Content,
			MediaIDs: req.MediaIDs,
		}
		if req.ThreadID != nil {
			interaction.ThreadID = req.ThreadID
		}
		data, _ := db.MarshalInteraction(interaction)
		postID, err := database.InsertInteraction(data)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		// Broadcast user message via SSE
		broker.Broadcast(sse.Event{Type: "new_post", Data: map[string]interface{}{
			"id":      postID,
			"content": req.Content,
			"type":    "user_message",
		}})

		// Get the provider and send prompt asynchronously
		provider, err := registry.Get(agentID)
		if err != nil {
			jsonError(w, "unknown agent: "+agentID, http.StatusBadRequest)
			return
		}

		threadID := postID
		if req.ThreadID != nil {
			threadID = *req.ThreadID
		}

		// Launch agent prompt in background, stream events via SSE
		go func() {
			// Forward agent events to SSE broker
			go func() {
				for event := range provider.Events() {
					broker.Broadcast(sse.Event{
						Type: "agent_" + event.Type,
						Data: event.Data,
					})
				}
			}()

			err := provider.Prompt(r.Context(), req.Content, threadID)
			if err != nil {
				broker.Broadcast(sse.Event{Type: "agent_error", Data: map[string]string{"error": err.Error()}})
				return
			}

			// Store agent response
			// (In a full implementation, we'd collect the streamed content)
			agentData := db.InteractionData{
				Type:     "agent_response",
				Content:  "(streamed response)",
				AgentID:  provider.ID(),
				ThreadID: &threadID,
			}
			respData, _ := db.MarshalInteraction(agentData)
			respID, _ := database.InsertInteraction(respData)

			broker.Broadcast(sse.Event{Type: "agent_response", Data: map[string]interface{}{
				"id":        respID,
				"thread_id": threadID,
				"agent_id":  provider.ID(),
			}})
		}()

		// Return immediately with the user post ID
		w.WriteHeader(http.StatusAccepted)
		jsonResp(w, map[string]interface{}{
			"id":        postID,
			"thread_id": threadID,
			"agent_id":  agentID,
			"status":    "queued",
		})
	}
}

func getWhitelist(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		patterns, err := database.GetWhitelist()
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		if patterns == nil {
			patterns = []string{}
		}
		jsonResp(w, map[string]interface{}{"patterns": patterns})
	}
}

func addWhitelist(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Pattern     string `json:"pattern"`
			Description string `json:"description"`
		}
		if err := decodeJSON(r, &req); err != nil {
			jsonError(w, "invalid body", http.StatusBadRequest)
			return
		}
		if req.Pattern == "" {
			jsonError(w, "pattern is required", http.StatusBadRequest)
			return
		}
		if err := database.AddWhitelistPattern(req.Pattern, req.Description); err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusCreated)
		jsonResp(w, map[string]string{"status": "added", "pattern": req.Pattern})
	}
}

func removeWhitelist(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Pattern string `json:"pattern"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.Pattern == "" {
			jsonError(w, "pattern is required", http.StatusBadRequest)
			return
		}
		if err := database.RemoveWhitelistPattern(req.Pattern); err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}
}
