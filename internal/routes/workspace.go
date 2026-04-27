package routes

import (
	"archive/zip"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/go-chi/chi/v5"
)

// Workspace mounts workspace file-management routes.
func Workspace(workDir string) func(r chi.Router) {
	return func(r chi.Router) {
		r.Get("/tree", getTree(workDir))
		r.Get("/file", getFile(workDir))
		r.Put("/file", putFile(workDir))
		r.Delete("/file", deleteFile(workDir))
		r.Post("/create", createFile(workDir))
		r.Post("/rename", renameFile(workDir))
		r.Get("/raw", getRaw(workDir))
		r.Get("/download", downloadPath(workDir))
		r.Post("/upload", uploadFile(workDir))
	}
}

// ── Tree ─────────────────────────────────────────────────────────

type fileEntry struct {
	Name     string      `json:"name"`
	Path     string      `json:"path"`
	Type     string      `json:"type"` // "file" or "directory"
	Size     int64       `json:"size,omitempty"`
	Children []fileEntry `json:"children,omitempty"`
}

func getTree(workDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		subpath := r.URL.Query().Get("path")
		depth := intQuery(r, "depth", 3)
		showHidden := r.URL.Query().Get("show_hidden") == "true"

		root := filepath.Join(workDir, filepath.Clean("/"+subpath))
		if !strings.HasPrefix(root, workDir) {
			jsonError(w, "path traversal", http.StatusBadRequest)
			return
		}

		entries := buildTree(root, workDir, depth, showHidden)
		jsonResp(w, map[string]interface{}{"entries": entries})
	}
}

func buildTree(dir, workDir string, depth int, showHidden bool) []fileEntry {
	if depth <= 0 {
		return nil
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}

	var result []fileEntry
	for _, e := range entries {
		name := e.Name()
		if !showHidden && strings.HasPrefix(name, ".") {
			continue
		}

		rel, _ := filepath.Rel(workDir, filepath.Join(dir, name))
		entry := fileEntry{Name: name, Path: rel}

		if e.IsDir() {
			entry.Type = "directory"
			if depth > 1 {
				entry.Children = buildTree(filepath.Join(dir, name), workDir, depth-1, showHidden)
			}
		} else {
			entry.Type = "file"
			if info, err := e.Info(); err == nil {
				entry.Size = info.Size()
			}
		}
		result = append(result, entry)
	}
	return result
}

// ── File CRUD ────────────────────────────────────────────────────

func getFile(workDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Query().Get("path")
		if path == "" {
			jsonError(w, "missing path", http.StatusBadRequest)
			return
		}

		fullPath := safePath(workDir, path)
		if fullPath == "" {
			jsonError(w, "invalid path", http.StatusBadRequest)
			return
		}

		info, err := os.Stat(fullPath)
		if err != nil {
			http.NotFound(w, r)
			return
		}
		if info.IsDir() {
			jsonError(w, "path is a directory", http.StatusBadRequest)
			return
		}

		maxBytes := int64(intQuery(r, "max_bytes", 100_000))
		data, err := readFileLimited(fullPath, maxBytes)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		// Detect if binary
		contentType := http.DetectContentType(data)
		isBinary := !strings.HasPrefix(contentType, "text/") &&
			contentType != "application/json" &&
			contentType != "application/javascript" &&
			contentType != "application/xml"

		resp := map[string]interface{}{
			"path":         path,
			"size":         info.Size(),
			"content_type": contentType,
			"truncated":    info.Size() > maxBytes,
		}
		if isBinary {
			resp["content"] = base64.StdEncoding.EncodeToString(data)
			resp["encoding"] = "base64"
		} else {
			resp["content"] = string(data)
			resp["encoding"] = "utf-8"
		}

		jsonResp(w, resp)
	}
}

func putFile(workDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Path    string `json:"path"`
			Content string `json:"content"`
		}
		if err := decodeJSON(r, &req); err != nil {
			jsonError(w, "invalid body", http.StatusBadRequest)
			return
		}

		fullPath := safePath(workDir, req.Path)
		if fullPath == "" {
			jsonError(w, "invalid path", http.StatusBadRequest)
			return
		}

		if err := os.MkdirAll(filepath.Dir(fullPath), 0o755); err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		if err := os.WriteFile(fullPath, []byte(req.Content), 0o644); err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		jsonResp(w, map[string]string{"status": "ok", "path": req.Path})
	}
}

func deleteFile(workDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Query().Get("path")
		fullPath := safePath(workDir, path)
		if fullPath == "" {
			jsonError(w, "invalid path", http.StatusBadRequest)
			return
		}

		if err := os.RemoveAll(fullPath); err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}
}

func createFile(workDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Path    string `json:"path"`
			Name    string `json:"name"`
			Content string `json:"content"`
			IsDir   bool   `json:"is_dir"`
		}
		if err := decodeJSON(r, &req); err != nil {
			jsonError(w, "invalid body", http.StatusBadRequest)
			return
		}

		target := filepath.Join(req.Path, req.Name)
		fullPath := safePath(workDir, target)
		if fullPath == "" {
			jsonError(w, "invalid path", http.StatusBadRequest)
			return
		}

		if req.IsDir {
			if err := os.MkdirAll(fullPath, 0o755); err != nil {
				jsonError(w, err.Error(), http.StatusInternalServerError)
				return
			}
		} else {
			if err := os.MkdirAll(filepath.Dir(fullPath), 0o755); err != nil {
				jsonError(w, err.Error(), http.StatusInternalServerError)
				return
			}
			if err := os.WriteFile(fullPath, []byte(req.Content), 0o644); err != nil {
				jsonError(w, err.Error(), http.StatusInternalServerError)
				return
			}
		}

		w.WriteHeader(http.StatusCreated)
		jsonResp(w, map[string]string{"status": "created", "path": target})
	}
}

func renameFile(workDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			From string `json:"from"`
			To   string `json:"to"`
		}
		if err := decodeJSON(r, &req); err != nil {
			jsonError(w, "invalid body", http.StatusBadRequest)
			return
		}

		fromPath := safePath(workDir, req.From)
		toPath := safePath(workDir, req.To)
		if fromPath == "" || toPath == "" {
			jsonError(w, "invalid path", http.StatusBadRequest)
			return
		}

		if err := os.MkdirAll(filepath.Dir(toPath), 0o755); err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		if err := os.Rename(fromPath, toPath); err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		jsonResp(w, map[string]string{"status": "ok", "from": req.From, "to": req.To})
	}
}

func getRaw(workDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Query().Get("path")
		fullPath := safePath(workDir, path)
		if fullPath == "" {
			http.NotFound(w, r)
			return
		}
		http.ServeFile(w, r, fullPath)
	}
}

func downloadPath(workDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Query().Get("path")
		fullPath := safePath(workDir, path)
		if fullPath == "" {
			http.NotFound(w, r)
			return
		}

		info, err := os.Stat(fullPath)
		if err != nil {
			http.NotFound(w, r)
			return
		}

		if !info.IsDir() {
			// Single file download
			w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s"`, info.Name()))
			http.ServeFile(w, r, fullPath)
			return
		}

		// Directory download as ZIP
		w.Header().Set("Content-Type", "application/zip")
		w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="%s.zip"`, info.Name()))

		zw := zip.NewWriter(w)
		defer zw.Close()

		filepath.Walk(fullPath, func(path string, fi os.FileInfo, err error) error {
			if err != nil || fi.IsDir() {
				return err
			}
			rel, _ := filepath.Rel(fullPath, path)
			fw, err := zw.Create(rel)
			if err != nil {
				return err
			}
			f, err := os.Open(path)
			if err != nil {
				return err
			}
			defer f.Close()
			_, err = io.Copy(fw, f)
			return err
		})
	}
}

func uploadFile(workDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseMultipartForm(50 << 20); err != nil {
			jsonError(w, "parse error: "+err.Error(), http.StatusBadRequest)
			return
		}

		targetPath := r.FormValue("path")
		file, header, err := r.FormFile("file")
		if err != nil {
			jsonError(w, "missing file", http.StatusBadRequest)
			return
		}
		defer file.Close()

		destPath := safePath(workDir, filepath.Join(targetPath, header.Filename))
		if destPath == "" {
			jsonError(w, "invalid path", http.StatusBadRequest)
			return
		}

		if err := os.MkdirAll(filepath.Dir(destPath), 0o755); err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		out, err := os.Create(destPath)
		if err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}
		defer out.Close()

		if _, err := io.Copy(out, file); err != nil {
			jsonError(w, err.Error(), http.StatusInternalServerError)
			return
		}

		rel, _ := filepath.Rel(workDir, destPath)
		w.WriteHeader(http.StatusCreated)
		jsonResp(w, map[string]string{"status": "uploaded", "path": rel})
	}
}

// ── Helpers ──────────────────────────────────────────────────────

// safePath resolves a relative path under workDir, preventing traversal.
func safePath(workDir, rel string) string {
	if rel == "" {
		return workDir
	}
	cleaned := filepath.Clean("/" + rel)
	full := filepath.Join(workDir, cleaned)
	if !strings.HasPrefix(full, workDir) {
		return ""
	}
	return full
}

func readFileLimited(path string, maxBytes int64) ([]byte, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return io.ReadAll(io.LimitReader(f, maxBytes))
}

// Export jsonResp/jsonError are in timeline.go — they share the package.
// (No duplication needed since they're in the same package.)
func init() {
	// Suppress unused import warning for json/fmt
	_ = json.Marshal
	_ = fmt.Sprintf
}
