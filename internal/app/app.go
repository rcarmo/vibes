package app

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
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

	// Serve frontend static files
	fileServer := http.FileServer(http.Dir("static"))
	r.Handle("/static/*", http.StripPrefix("/static/", fileServer))
	r.Get("/", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "static/index.html")
	})

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
