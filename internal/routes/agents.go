package routes

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/db"
	"github.com/rcarmo/vibes/internal/server/sse"
)

// Agents mounts agent-related routes.
func Agents(registry *agent.Registry, database *db.DB, broker *sse.Broker) func(r chi.Router) {
	permissionBroker := NewPermissionBroker(broker, 30*time.Second)
	queue := NewFollowUpQueue()
	return func(r chi.Router) {
		r.Get("/", listAgents(registry))
		r.Get("/status", getAgentStatus(registry))
		r.Post("/{id}/message", sendAgentMessage(registry, database, broker))
		r.Get("/models", getAgentModels(registry))
		r.Get("/queue", getQueue(queue))
		r.Post("/queue-remove", removeQueueItem(queue))
		r.Post("/queue-steer", steerQueueItem(queue))
		r.Get("/turn/{id}", getTurnPreview())
		r.Post("/turn/{id}/panel", setTurnPanel())
		r.Post("/respond", permissionBroker.RespondHandler())
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
			"status":           status.State,
			"model":            status.Model,
			"context_pct":      status.ContextPct,
			"agent_id":         p.ID(),
			"active_turns":     []interface{}{},
			"queued_followups": []interface{}{},
			"pending_steers":   []interface{}{},
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

		// Validate the provider before storing the user message.
		provider, err := registry.Get(agentID)
		if err != nil {
			jsonError(w, "unknown agent: "+agentID, http.StatusBadRequest)
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

		threadID := postID
		if req.ThreadID != nil {
			threadID = *req.ThreadID
		}

		// Launch agent prompt in background, collect streamed content
		promptCtx := context.Background()
		go func() {
			// Collect streamed draft text during the turn (fixes #1)
			var collectedContent strings.Builder
			collectDone := make(chan struct{})

			go func() {
				defer close(collectDone)
				for event := range provider.Events() {
					// Accumulate draft text
					if event.Type == "draft" {
						if m, ok := event.Data.(map[string]string); ok {
							if text, exists := m["text"]; exists {
								collectedContent.WriteString(text)
							}
						}
					}
					// All events still forwarded via central event loop in app.go
				}
			}()

			err := provider.Prompt(promptCtx, req.Content, threadID)
			<-collectDone

			if err != nil {
				broker.Broadcast(sse.Event{Type: "agent_error", Data: map[string]string{"error": err.Error()}})
				return
			}

			// Store final agent response with collected content
			finalContent := collectedContent.String()
			if finalContent == "" {
				finalContent = "(no content)"
			}
			agentData := db.InteractionData{
				Type:     "agent_response",
				Content:  finalContent,
				AgentID:  provider.ID(),
				ThreadID: &threadID,
				Model:    provider.Status().Model,
			}
			respData, _ := db.MarshalInteraction(agentData)
			respID, _ := database.InsertInteraction(respData)

			broker.Broadcast(sse.Event{Type: "agent_response", Data: map[string]interface{}{
				"id":        respID,
				"thread_id": threadID,
				"agent_id":  provider.ID(),
				"content":   finalContent,
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

func getAgentModels(registry *agent.Registry) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		p, err := registry.Get("default")
		if err != nil {
			jsonResp(w, map[string]interface{}{"current": "", "models": []string{}})
			return
		}
		status := p.Status()
		models := []string{}
		if status.Model != "" {
			models = append(models, status.Model)
		}
		jsonResp(w, map[string]interface{}{"current": status.Model, "model": status.Model, "models": models})
	}
}

func getQueue(queue *FollowUpQueue) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		jsonResp(w, map[string]interface{}{"items": queue.List(), "queued_followups": queue.List()})
	}
}

func removeQueueItem(queue *FollowUpQueue) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			RowID int64 `json:"row_id"`
		}
		if err := decodeJSON(r, &req); err != nil || req.RowID == 0 {
			jsonError(w, "row_id required", http.StatusBadRequest)
			return
		}
		if !queue.Remove(req.RowID) {
			jsonError(w, "queue item not found", http.StatusNotFound)
			return
		}
		jsonResp(w, map[string]string{"status": "removed"})
	}
}

func steerQueueItem(queue *FollowUpQueue) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			RowID int64 `json:"row_id"`
		}
		if err := decodeJSON(r, &req); err != nil || req.RowID == 0 {
			jsonError(w, "row_id required", http.StatusBadRequest)
			return
		}
		if !queue.PromoteToSteer(req.RowID) {
			jsonError(w, "queue item not found", http.StatusNotFound)
			return
		}
		jsonResp(w, map[string]string{"status": "steered"})
	}
}

func getTurnPreview() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		jsonResp(w, map[string]interface{}{
			"draft": "", "draft_total_lines": 0,
			"thought": "", "thought_total_lines": 0,
		})
	}
}

func setTurnPanel() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		jsonResp(w, map[string]string{"status": "ok"})
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
