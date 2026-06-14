package routes

import (
	"fmt"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/db"
	"github.com/rcarmo/vibes/internal/server/sse"
)

// SetThreadBackend returns a handler for switching a thread's backend affinity.
func SetThreadBackend(database *db.DB, registry *agent.Registry, broker *sse.Broker) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		threadID, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
		if err != nil || threadID == 0 {
			jsonError(w, "invalid thread id", http.StatusBadRequest)
			return
		}
		var req struct {
			BackendID string `json:"backend_id"`
		}
		if err := decodeJSON(r, &req); err != nil || req.BackendID == "" {
			jsonError(w, "backend_id is required", http.StatusBadRequest)
			return
		}
		descriptor, ok := registry.Descriptor(req.BackendID)
		if !ok || !descriptor.Available {
			jsonError(w, "backend is not available", http.StatusBadRequest)
			return
		}
		current, err := database.GetThreadBackend(threadID)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		from := ""
		if current != nil {
			from = current.Backend.ID
		}
		backend := db.BackendMetadata{
			ID:        descriptor.ID,
			Family:    descriptor.Family,
			Transport: descriptor.Transport,
			Label:     descriptor.Label,
			Model:     descriptor.Model,
			Mode:      "thread_backend",
		}
		stored, changed, err := database.SetThreadBackend(threadID, backend)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		if changed && from != "" && from != stored.Backend.ID {
			content := fmt.Sprintf("Backend switched from %s to %s.", from, stored.Backend.ID)
			payload := db.InteractionData{
				Type:     "system",
				Content:  content,
				ThreadID: &threadID,
				BackendSwitch: &db.BackendSwitch{
					From:                    from,
					To:                      stored.Backend.ID,
					ThreadBackendGeneration: stored.BackendGeneration,
				},
			}
			data, _ := db.MarshalInteraction(payload)
			postID, err := database.InsertInteraction(data)
			if err == nil {
				if interaction, err := database.GetInteraction(postID); err == nil {
					broker.Broadcast(sse.Event{Type: "new_post", Data: interaction})
				}
			}
		}
		jsonResp(w, map[string]interface{}{
			"status":             "ok",
			"thread_id":          threadID,
			"backend":            stored.Backend,
			"backend_generation": stored.BackendGeneration,
			"changed":            changed,
		})
	}
}

// GetThreadBackend returns a handler for reading a thread's backend affinity.
func GetThreadBackend(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		threadID, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
		if err != nil || threadID == 0 {
			jsonError(w, "invalid thread id", http.StatusBadRequest)
			return
		}
		backend, err := database.GetThreadBackend(threadID)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		if backend == nil {
			jsonResp(w, map[string]interface{}{"thread_id": threadID, "backend": nil})
			return
		}
		jsonResp(w, backend)
	}
}
