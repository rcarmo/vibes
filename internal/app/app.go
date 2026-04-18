package app

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	vibes "github.com/rcarmo/vibes"
	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/config"
	"github.com/rcarmo/vibes/internal/extensions"
)

// App is the top-level application container.
type App struct {
	Config     *config.Config
	Router     chi.Router
	Agents     *agent.Registry
	Extensions *extensions.Registry
}

// New creates and wires the application.
func New(cfg *config.Config) (*App, error) {
	app := &App{
		Config:     cfg,
		Agents:     agent.NewRegistry(),
		Extensions: extensions.NewRegistry(),
	}

	// Set up HTTP router
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(corsMiddleware)

	// Health
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"status":"ok"}`))
	})

	// TODO: mount route groups
	// r.Route("/timeline", routes.Timeline(app))
	// r.Route("/media", routes.Media(app))
	// r.Route("/workspace", routes.Workspace(app))
	// r.Route("/agent", routes.Agents(app))
	// r.Get("/sse/stream", sse.Handler(app))

	// Mount extension routes
	for _, route := range app.Extensions.AllRoutes() {
		slog.Debug("mounting extension route", "method", route.Method, "pattern", route.Pattern)
		r.Method(route.Method, route.Pattern, route.Handler)
	}

	// Serve frontend static files (embedded into the binary at compile time).
	staticFS, err := vibes.StaticFS()
	if err != nil {
		return nil, fmt.Errorf("load embedded static FS: %w", err)
	}
	fileServer := http.FileServer(staticFS)
	r.Handle("/static/*", http.StripPrefix("/static/", fileServer))

	// Serve index.html at the root
	r.Get("/", serveStaticFile(staticFS, "index.html", "text/html; charset=utf-8"))
	r.Get("/index.html", serveStaticFile(staticFS, "index.html", "text/html; charset=utf-8"))
	r.Get("/manifest.json", serveStaticFile(staticFS, "manifest.json", "application/manifest+json"))
	r.Get("/icon-192.png", serveStaticFile(staticFS, "icon-192.png", "image/png"))
	r.Get("/icon-512.png", serveStaticFile(staticFS, "icon-512.png", "image/png"))

	app.Router = r
	return app, nil
}

// Run starts the HTTP server and blocks until the context is cancelled.
func (app *App) Run(ctx context.Context) error {
	// Initialize extensions
	if err := app.Extensions.InitAll(ctx); err != nil {
		return fmt.Errorf("init extensions: %w", err)
	}
	defer app.Extensions.ShutdownAll(context.Background())

	addr := fmt.Sprintf("%s:%d", app.Config.Host, app.Config.Port)
	server := &http.Server{
		Addr:    addr,
		Handler: app.Router,
	}

	// Graceful shutdown
	go func() {
		<-ctx.Done()
		slog.Info("shutting down server")
		server.Shutdown(context.Background())
	}()

	slog.Info("listening", "addr", addr)
	if err := server.ListenAndServe(); err != http.ErrServerClosed {
		return err
	}
	return nil
}

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// serveStaticFile returns a handler that serves a single file from the embedded FS.
func serveStaticFile(fs http.FileSystem, name, contentType string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		f, err := fs.Open(name)
		if err != nil {
			http.NotFound(w, r)
			return
		}
		defer f.Close()

		stat, err := f.Stat()
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		if contentType != "" {
			w.Header().Set("Content-Type", contentType)
		}
		http.ServeContent(w, r, name, stat.ModTime(), f)
	}
}
