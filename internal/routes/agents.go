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
	permissionBroker := NewPermissionBroker(broker, 30*time.Second, database)
	queue := NewFollowUpQueue()
	turnMgr := NewTurnManager()
	return func(r chi.Router) {
		r.Get("/", listAgents(registry))
		r.Get("/status", getAgentStatus(registry))
		r.Get("/providers", getProviders(registry))
		r.Post("/providers/{id}/activate", activateProvider(registry))
		r.Post("/{id}/message", sendAgentMessage(registry, database, broker))
		r.Get("/models", getAgentModels(registry))
		r.Get("/queue", getQueue(queue))
		r.Post("/queue-remove", removeQueueItem(queue))
		r.Post("/queue-steer", steerQueueItem(queue))
		r.Get("/turn/{id}", getTurnPreviewHandler(turnMgr))
		r.Post("/turn/{id}/panel", setTurnPanelHandler(turnMgr))
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

func getProviders(registry *agent.Registry) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		jsonResp(w, map[string]interface{}{
			"providers": registry.Descriptors(),
			"active":    registry.Active(),
		})
	}
}

func activateProvider(registry *agent.Registry) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		if id == "" {
			jsonError(w, "provider id is required", http.StatusBadRequest)
			return
		}
		if err := registry.SetActive(id); err != nil {
			jsonError(w, err.Error(), http.StatusBadRequest)
			return
		}
		jsonResp(w, map[string]interface{}{"status": "ok", "active": id})
	}
}

func sendAgentMessage(registry *agent.Registry, database *db.DB, broker *sse.Broker) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		agentID := chi.URLParam(r, "id")

		var req struct {
			Content   string                     `json:"content"`
			ThreadID  *int64                     `json:"thread_id"`
			MediaIDs  []int64                    `json:"media_ids"`
			BackendID string                     `json:"backend_id"`
			Context   []agent.PromptResourceLink `json:"context"`
		}
		if err := decodeJSON(r, &req); err != nil {
			jsonError(w, "invalid body", http.StatusBadRequest)
			return
		}
		if req.Content == "" {
			jsonError(w, "content is required", http.StatusBadRequest)
			return
		}

		selectedAgentID := strings.TrimSpace(req.BackendID)
		if selectedAgentID == "" {
			selectedAgentID = agentID
		}
		if selectedAgentID == "default" && req.ThreadID != nil {
			if tb, err := database.GetThreadBackend(*req.ThreadID); err == nil && tb != nil && tb.Backend.ID != "" {
				selectedAgentID = tb.Backend.ID
			}
		}

		// Handle built-in slash commands locally before touching the timeline/agent.
		if cmd, handled := HandleSlashCommand(req.Content, SlashCommandEnv{Registry: registry, DB: database, BackendID: selectedAgentID}); handled {
			if cmd.Action == "clear" {
				jsonResp(w, map[string]interface{}{
					"status":  "command",
					"command": cmd,
				})
				return
			}
			if strings.TrimSpace(cmd.Message) != "" {
				provider, _ := registry.Get(selectedAgentID)
				providerID := selectedAgentID
				model := ""
				if provider != nil {
					providerID = provider.ID()
					model = provider.Status().Model
				}
				postID, eventData, err := storeLocalAgentResponse(database, cmd, registry, providerID, model)
				if err != nil {
					jsonError(w, err.Error(), http.StatusInternalServerError)
					return
				}
				broker.Broadcast(sse.Event{Type: "agent_response", Data: eventData})
				jsonResp(w, map[string]interface{}{
					"id":      postID,
					"status":  "command",
					"command": cmd,
				})
				return
			}
			jsonResp(w, map[string]interface{}{
				"status":  "command",
				"command": cmd,
			})
			return
		}

		// Validate the provider before storing the user message.
		provider, err := registry.Get(selectedAgentID)
		if err != nil {
			jsonError(w, "unknown agent: "+selectedAgentID, http.StatusBadRequest)
			return
		}

		backendMeta := backendMetadataFor(registry, selectedAgentID, provider.Status().Model, "prompt")
		backendMeta.ThreadBackendGeneration = 1
		threadID := int64(0)
		if req.ThreadID != nil {
			threadID = *req.ThreadID
			threadBackend, changedBackend, previousBackend, err := switchThreadBackend(database, registry, threadID, backendMeta.ID)
			if err != nil {
				jsonError(w, err.Error(), http.StatusInternalServerError)
				return
			}
			if threadBackend != nil {
				backendMeta.ThreadBackendGeneration = threadBackend.BackendGeneration
			}
			if changedBackend && previousBackend != "" && previousBackend != backendMeta.ID {
				_ = recordBackendSwitch(database, broker, threadID, previousBackend, backendMeta.ID, backendMeta.ThreadBackendGeneration)
			}
		}

		// Store the user message
		interaction := db.InteractionData{
			Type:     "user_message",
			Content:  req.Content,
			MediaIDs: req.MediaIDs,
			Backend:  &backendMeta,
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

		if threadID == 0 {
			threadID = postID
			threadBackend, _, _, err := switchThreadBackend(database, registry, threadID, backendMeta.ID)
			if err != nil {
				jsonError(w, err.Error(), http.StatusInternalServerError)
				return
			}
			if threadBackend != nil {
				backendMeta.ThreadBackendGeneration = threadBackend.BackendGeneration
			}
		}

		// Broadcast user message via SSE
		if post, err := database.GetInteraction(postID); err == nil {
			broker.Broadcast(sse.Event{Type: "new_post", Data: post})
		}

		// Launch agent prompt in background
		promptCtx := context.Background()
		go func() {
			promptReq := agent.PromptRequest{Text: req.Content, ThreadID: threadID, ResourceLinks: req.Context}
			var err error
			if richProvider, ok := provider.(agent.RichPromptProvider); ok {
				err = richProvider.PromptRequest(promptCtx, promptReq)
			} else {
				err = provider.Prompt(promptCtx, req.Content, threadID)
			}
			if err != nil {
				broker.Broadcast(sse.Event{Type: "agent_error", Data: map[string]string{"error": err.Error()}})
				return
			}

			// Collect final content from the provider's draft accumulator
			type draftCollector interface {
				CollectedDraft() string
			}
			finalContent := "(response delivered via streaming)"
			if dc, ok := provider.(draftCollector); ok {
				if draft := dc.CollectedDraft(); draft != "" {
					finalContent = draft
				}
			}

			responseBackend := backendMetadataFor(registry, selectedAgentID, provider.Status().Model, "response")
			responseBackend.ThreadBackendGeneration = backendMeta.ThreadBackendGeneration

			// Store agent response (content was streamed via SSE draft events)
			agentData := db.InteractionData{
				Type:     "agent_response",
				Content:  finalContent,
				AgentID:  provider.ID(),
				ThreadID: &threadID,
				Model:    provider.Status().Model,
				Backend:  &responseBackend,
			}
			respData, _ := db.MarshalInteraction(agentData)
			respID, _ := database.InsertInteraction(respData)

			if post, err := database.GetInteraction(respID); err == nil {
				broker.Broadcast(sse.Event{Type: "agent_response", Data: post})
			}
		}()

		// Return immediately with the user post ID
		w.WriteHeader(http.StatusAccepted)
		jsonResp(w, map[string]interface{}{
			"id":        postID,
			"thread_id": threadID,
			"agent_id":  selectedAgentID,
			"backend":   backendMeta,
			"status":    "queued",
		})
	}
}

func backendMetadataFor(registry *agent.Registry, providerID, model, mode string) db.BackendMetadata {
	descriptor, ok := registry.Descriptor(providerID)
	if !ok && providerID == "default" {
		descriptor, ok = registry.Descriptor(registry.Active())
	}
	meta := db.BackendMetadata{ID: providerID, Model: model, Mode: mode}
	if ok {
		meta.ID = descriptor.ID
		meta.Family = descriptor.Family
		meta.Transport = descriptor.Transport
		meta.Label = descriptor.Label
		if meta.Model == "" {
			meta.Model = descriptor.Model
		}
	}
	return meta
}

func storeLocalAgentResponse(database *db.DB, cmd *SlashCommandResult, registry *agent.Registry, providerID, model string) (int64, map[string]interface{}, error) {
	backend := backendMetadataFor(registry, providerID, model, "local_command")
	payload := db.InteractionData{
		Type:    "agent_response",
		Content: cmd.Message,
		AgentID: providerID,
		Model:   model,
		Backend: &backend,
	}
	data, err := db.MarshalInteraction(payload)
	if err != nil {
		return 0, nil, err
	}
	id, err := database.InsertInteraction(data)
	if err != nil {
		return 0, nil, err
	}
	interaction, err := database.GetInteraction(id)
	if err != nil {
		return 0, nil, err
	}
	eventData := map[string]interface{}{
		"id":        interaction.ID,
		"timestamp": interaction.Timestamp,
		"data":      interaction.Data,
	}
	if cmd.UserName != "" {
		eventData["user_name"] = cmd.UserName
	}
	if cmd.UserAvatar != "" {
		eventData["user_avatar"] = cmd.UserAvatar
	}
	if cmd.UserAvatarBackground != "" {
		eventData["user_avatar_background"] = cmd.UserAvatarBackground
	}
	if cmd.ModelLabel != "" {
		eventData["model"] = cmd.ModelLabel
	}
	if cmd.ThinkingLevel != "" {
		eventData["thinking_level"] = cmd.ThinkingLevel
	}
	if cmd.SupportsThinking {
		eventData["supports_thinking"] = true
	}
	eventData["backend"] = backend
	return id, eventData, nil
}

func getAgentModels(registry *agent.Registry) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		p, err := registry.Get("default")
		if err != nil {
			jsonResp(w, map[string]interface{}{"current": "", "models": []string{}})
			return
		}
		status := p.Status()

		// Collect models from all registered agents (fixes #7)
		var models []map[string]string
		for _, id := range registry.List() {
			ap, _ := registry.Get(id)
			s := ap.Status()
			if s.Model != "" {
				models = append(models, map[string]string{
					"agent_id": id,
					"model":    s.Model,
				})
			}
		}
		if models == nil {
			models = []map[string]string{}
		}

		jsonResp(w, map[string]interface{}{
			"current": status.Model,
			"model":   status.Model,
			"models":  models,
		})
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
