package app

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	vibes "github.com/rcarmo/vibes"
	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/agent/acp"
	"github.com/rcarmo/vibes/internal/agent/pi"
	"github.com/rcarmo/vibes/internal/config"
	"github.com/rcarmo/vibes/internal/db"
	"github.com/rcarmo/vibes/internal/extensions"
	"github.com/rcarmo/vibes/internal/routes"
	"github.com/rcarmo/vibes/internal/server/sse"
)

// App is the top-level application container.
type App struct {
	Config     *config.Config
	Router     chi.Router
	DB         *db.DB
	Agents     *agent.Registry
	Extensions *extensions.Registry
	SSE        *sse.Broker
}

// New creates and wires the application.
func New(cfg *config.Config) (*App, error) {
	// Open database
	database, err := db.Open(cfg.DBPath)
	if err != nil {
		return nil, fmt.Errorf("open database: %w", err)
	}

	// Create SSE broker
	broker := sse.NewBroker()

	// Create agent registry
	agentRegistry := agent.NewRegistry()

	// Register ACP agent from config
	if cfg.ACPAgent != "" {
		parts := splitCommand(cfg.ACPAgent)
		acpProvider := acp.New(acp.Config{
			ID:      "acp",
			Command: parts[0],
			Args:    parts[1:],
			WorkDir: workspaceDir(),
		})
		agentRegistry.Register("acp", acpProvider)
	}

	// Register Pi native RPC agent if enabled
	if cfg.PiEnabled {
		piCmd := cfg.PiAgent
		if piCmd == "" {
			piCmd = "pi"
		}
		piProvider := pi.New(pi.Config{
			Command: piCmd,
			WorkDir: workspaceDir(),
		})
		agentRegistry.Register("pi", piProvider)
		if cfg.DefaultAgent == "pi" {
			agentRegistry.SetActive("pi")
		}
	}

	app := &App{
		Config:     cfg,
		DB:         database,
		Agents:     agentRegistry,
		Extensions: extensions.NewRegistry(),
		SSE:        broker,
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

	// API routes
	r.Route("/timeline", routes.Timeline(database))
	r.Route("/post", routes.Posts(database))
	r.Route("/thread", routes.Threads(database))
	r.Route("/search", routes.Search(database))
	r.Route("/media", routes.Media(database))
	r.Route("/workspace", routes.Workspace(workspaceDir()))
	r.Route("/agent", routes.Agents(agentRegistry, database, broker))
	r.Get("/agent/commands", routes.GetCommands())
	r.Get("/agent/context", func(w http.ResponseWriter, r *http.Request) {
		p, err := agentRegistry.Get("default")
		if err != nil {
			jsonResp := func(w http.ResponseWriter, v interface{}) {
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(v)
			}
			jsonResp(w, map[string]interface{}{"used": 0, "total": 0, "pct": 0})
			return
		}
		s := p.Status()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{"used": 0, "total": 1000000, "pct": s.ContextPct})
	})
	r.Get("/agents", func(w http.ResponseWriter, r *http.Request) {
		// Alias for /agent/ list
		routes.Agents(agentRegistry, database, broker)(chi.NewRouter())
		ids := agentRegistry.List()
		agents := make([]map[string]interface{}, 0)
		for _, id := range ids {
			p, _ := agentRegistry.Get(id)
			s := p.Status()
			agents = append(agents, map[string]interface{}{
				"id": id, "status": s.State, "model": s.Model, "active": id == agentRegistry.Active(),
			})
		}
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprintf(w, `[`)
		for i, a := range agents {
			if i > 0 {
				fmt.Fprintf(w, ",")
			}
			b, _ := json.Marshal(a)
			w.Write(b)
		}
		fmt.Fprintf(w, `]`)
	})

	// SSE stream
	r.Get("/sse/stream", broker.Handler())

	// Extension routes
	for _, route := range app.Extensions.AllRoutes() {
		slog.Debug("mounting extension route", "method", route.Method, "pattern", route.Pattern)
		r.Method(route.Method, route.Pattern, route.Handler)
	}

	// Serve embedded static frontend
	staticFS, err := vibes.StaticFS()
	if err != nil {
		return nil, fmt.Errorf("load embedded static FS: %w", err)
	}
	fileServer := http.FileServer(staticFS)
	r.Handle("/static/*", http.StripPrefix("/static/", fileServer))
	r.Get("/", serveStaticFile(staticFS, "index.html", "text/html; charset=utf-8"))
	r.Get("/index.html", serveStaticFile(staticFS, "index.html", "text/html; charset=utf-8"))
	r.Get("/manifest.json", serveStaticFile(staticFS, "manifest.json", "application/manifest+json"))
	r.Get("/icon-192.png", serveStaticFile(staticFS, "icon-192.png", "image/png"))
	r.Get("/icon-512.png", serveStaticFile(staticFS, "icon-512.png", "image/png"))

	// Avatars
	r.Get("/avatar/{kind}", func(w http.ResponseWriter, r *http.Request) {
		kind := chi.URLParam(r, "kind")
		if kind == "agent" {
			serveStaticFile(staticFS, "icon-192.png", "image/png")(w, r)
		} else {
			http.NotFound(w, r)
		}
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
	defer app.DB.Close()

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

// splitCommand splits a command string by spaces (simple, no quotes).
func splitCommand(cmd string) []string {
	var parts []string
	var current string
	for _, c := range cmd {
		if c == ' ' {
			if current != "" {
				parts = append(parts, current)
				current = ""
			}
		} else {
			current += string(c)
		}
	}
	if current != "" {
		parts = append(parts, current)
	}
	return parts
}

// workspaceDir returns the workspace directory (cwd or VIBES_WORKSPACE).
func workspaceDir() string {
	if ws := os.Getenv("VIBES_WORKSPACE"); ws != "" {
		return ws
	}
	dir, _ := os.Getwd()
	return dir
}
