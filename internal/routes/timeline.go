// Package routes implements the HTTP API handlers for Vibes.
package routes

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/rcarmo/vibes/internal/db"
)

// Timeline mounts the timeline/thread/search routes.
func Timeline(database *db.DB) func(r chi.Router) {
	return func(r chi.Router) {
		r.Get("/", getTimeline(database))
		r.Post("/", createPost(database))
	}
}

// Posts mounts post-level routes.
func Posts(database *db.DB) func(r chi.Router) {
	return func(r chi.Router) {
		r.Get("/", getTimeline(database))
		r.Post("/", createPost(database))
		r.Delete("/{id}", deletePost(database))
	}
}

// Threads mounts thread routes.
func Threads(database *db.DB) func(r chi.Router) {
	return func(r chi.Router) {
		r.Get("/{id}", getThread(database))
		r.Post("/", createReply(database))
	}
}

// Search mounts the search route.
func Search(database *db.DB) func(r chi.Router) {
	return func(r chi.Router) {
		r.Get("/", searchPosts(database))
	}
}

// Hashtags mounts hashtag search routes.
func Hashtags(database *db.DB) func(r chi.Router) {
	return func(r chi.Router) {
		r.Get("/{tag}", getHashtag(database))
	}
}

func getTimeline(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		limit := intQuery(r, "limit", 20)
		var beforeID *int64
		if b := r.URL.Query().Get("before_id"); b != "" {
			if id, err := strconv.ParseInt(b, 10, 64); err == nil {
				beforeID = &id
			}
		}

		posts, err := database.GetTimeline(limit, beforeID)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		if posts == nil {
			posts = []db.Interaction{}
		}
		jsonResp(w, map[string]interface{}{"posts": posts})
	}
}

func getThread(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
		if err != nil {
			jsonError(w, "invalid thread id", http.StatusBadRequest)
			return
		}
		posts, err := database.GetThread(id)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		jsonResp(w, map[string]interface{}{"posts": posts})
	}
}

func searchPosts(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query().Get("q")
		if query == "" {
			jsonError(w, "missing q parameter", http.StatusBadRequest)
			return
		}
		limit := intQuery(r, "limit", 50)
		offset := intQuery(r, "offset", 0)

		posts, err := database.SearchInteractions(query, limit, offset)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		if posts == nil {
			posts = []db.Interaction{}
		}
		jsonResp(w, map[string]interface{}{"posts": posts})
	}
}

func getHashtag(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		tag := chi.URLParam(r, "tag")
		if tag == "" {
			jsonError(w, "missing hashtag", http.StatusBadRequest)
			return
		}
		limit := intQuery(r, "limit", 50)
		offset := intQuery(r, "offset", 0)

		posts, err := database.GetHashtag(tag, limit, offset)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		if posts == nil {
			posts = []db.Interaction{}
		}
		jsonResp(w, map[string]interface{}{"posts": posts})
	}
}

func createPost(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Content  string  `json:"content"`
			MediaIDs []int64 `json:"media_ids"`
		}
		if err := decodeJSON(r, &req); err != nil {
			jsonError(w, "invalid request body", http.StatusBadRequest)
			return
		}
		if req.Content == "" {
			jsonError(w, "content is required", http.StatusBadRequest)
			return
		}

		data, _ := db.MarshalInteraction(db.NewUserMessage(req.Content, req.MediaIDs))
		id, err := database.InsertInteraction(data)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		w.WriteHeader(http.StatusCreated)
		jsonResp(w, map[string]interface{}{"id": id})
	}
}

func createReply(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			ThreadID int64   `json:"thread_id"`
			Content  string  `json:"content"`
			MediaIDs []int64 `json:"media_ids"`
		}
		if err := decodeJSON(r, &req); err != nil {
			jsonError(w, "invalid request body", http.StatusBadRequest)
			return
		}
		if req.Content == "" || req.ThreadID == 0 {
			jsonError(w, "content and thread_id are required", http.StatusBadRequest)
			return
		}

		interaction := db.InteractionData{
			Type:     "user_message",
			Content:  req.Content,
			ThreadID: &req.ThreadID,
			MediaIDs: req.MediaIDs,
		}
		data, _ := db.MarshalInteraction(interaction)
		id, err := database.InsertInteraction(data)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		w.WriteHeader(http.StatusCreated)
		jsonResp(w, map[string]interface{}{"id": id})
	}
}

func deletePost(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
		if err != nil {
			jsonError(w, "invalid post id", http.StatusBadRequest)
			return
		}
		cascade := r.URL.Query().Get("cascade") == "true"
		ids := []int64{id}
		if cascade {
			if posts, err := database.GetThread(id); err == nil {
				ids = ids[:0]
				for _, post := range posts {
					ids = append(ids, post.ID)
				}
			}
		}

		if err := database.DeleteInteraction(id, cascade); err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}
}

// ── Helpers ──────────────────────────────────────────────────────

func intQuery(r *http.Request, key string, def int) int {
	v := r.URL.Query().Get(key)
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

func jsonResp(w http.ResponseWriter, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

func jsonError(w http.ResponseWriter, msg string, code int) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(map[string]string{"error": msg})
}

func decodeJSON(r *http.Request, v interface{}) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, 10<<20)) // 10 MB max
	if err != nil {
		return err
	}
	return json.Unmarshal(body, v)
}
