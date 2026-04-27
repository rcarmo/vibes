package routes

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/rcarmo/vibes/internal/db"
)

// Media mounts media routes.
func Media(database *db.DB) func(r chi.Router) {
	return func(r chi.Router) {
		r.Post("/upload", uploadMedia(database))
		r.Get("/{id}", getMedia(database))
		r.Get("/{id}/thumbnail", getMediaThumbnail(database))
		r.Get("/{id}/info", getMediaInfo(database))
	}
}

func uploadMedia(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// Parse multipart form (max 50 MB)
		if err := r.ParseMultipartForm(50 << 20); err != nil {
			jsonError(w, "failed to parse form: "+err.Error(), http.StatusBadRequest)
			return
		}

		file, header, err := r.FormFile("file")
		if err != nil {
			jsonError(w, "missing file field", http.StatusBadRequest)
			return
		}
		defer file.Close()

		data, err := io.ReadAll(io.LimitReader(file, 50<<20))
		if err != nil {
			jsonError(w, "failed to read file", http.StatusInternalServerError)
			return
		}

		contentType := header.Header.Get("Content-Type")
		if contentType == "" {
			contentType = http.DetectContentType(data)
		}

		// Generate thumbnail for images
		var thumbnail []byte
		if isImage(contentType) {
			thumbnail = generateThumbnail(data, contentType)
		}

		metadata, _ := json.Marshal(map[string]interface{}{
			"size":     len(data),
			"filename": header.Filename,
		})

		id, err := database.InsertMedia(header.Filename, contentType, data, thumbnail, metadata)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		w.WriteHeader(http.StatusCreated)
		jsonResp(w, map[string]interface{}{
			"id":           id,
			"filename":     header.Filename,
			"content_type": contentType,
			"url":          fmt.Sprintf("/media/%d", id),
			"thumbnail":    fmt.Sprintf("/media/%d/thumbnail", id),
		})
	}
}

func getMedia(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
		if err != nil {
			http.NotFound(w, r)
			return
		}

		media, err := database.GetMedia(id)
		if err != nil {
			http.NotFound(w, r)
			return
		}

		w.Header().Set("Content-Type", media.ContentType)
		w.Header().Set("Content-Disposition", fmt.Sprintf(`inline; filename="%s"`, media.Filename))
		w.Header().Set("Cache-Control", "public, max-age=86400")
		w.Write(media.Data)
	}
}

func getMediaThumbnail(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
		if err != nil {
			http.NotFound(w, r)
			return
		}

		media, err := database.GetMedia(id)
		if err != nil || media.Thumbnail == nil {
			http.NotFound(w, r)
			return
		}

		w.Header().Set("Content-Type", media.ContentType)
		w.Header().Set("Cache-Control", "public, max-age=86400")
		w.Write(media.Thumbnail)
	}
}

func getMediaInfo(database *db.DB) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
		if err != nil {
			http.NotFound(w, r)
			return
		}

		info, err := database.GetMediaInfo(id)
		if err != nil {
			http.NotFound(w, r)
			return
		}
		jsonResp(w, info)
	}
}

// ── Image helpers ────────────────────────────────────────────────

func isImage(contentType string) bool {
	switch contentType {
	case "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml":
		return true
	}
	return false
}

// generateThumbnail creates a downscaled version of an image.
// For now, we just return the original data for small images
// and skip for large ones. A proper implementation would use
// golang.org/x/image for resize.
func generateThumbnail(data []byte, contentType string) []byte {
	// Simple threshold: if under 200KB, use as-is for thumbnail
	if len(data) <= 200*1024 {
		return data
	}
	// TODO: proper image downscaling with golang.org/x/image
	// For now, return nil (no thumbnail for large images)
	return nil
}
