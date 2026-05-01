package app

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"sync"
	"time"

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

	// Create agent registry
	agentRegistry := agent.NewRegistry()

	// Create SSE broker with disconnect handling (fixes #9)
	broker := sse.NewBroker()
	var disconnectTimer *time.Timer
	var disconnectMu sync.Mutex

	broker.OnEmpty(func() {
		disconnectMu.Lock()
		defer disconnectMu.Unlock()
		timeout := time.Duration(cfg.DisconnectTimeout) * time.Second
		if timeout <= 0 {
			return
		}
		slog.Info("all SSE clients disconnected, starting disconnect timer", "timeout", timeout)
		disconnectTimer = time.AfterFunc(timeout, func() {
			slog.Info("disconnect timeout expired, shutting down agents")
			for _, id := range agentRegistry.List() {
				if p, err := agentRegistry.Get(id); err == nil {
					p.Shutdown(context.Background())
				}
			}
		})
	})

	broker.OnReconnect(func() {
		disconnectMu.Lock()
		defer disconnectMu.Unlock()
		if disconnectTimer != nil {
			disconnectTimer.Stop()
			disconnectTimer = nil
			slog.Info("SSE client reconnected, cancelled disconnect timer")
		}
	})

	// Register ACP agent from config
	if cfg.ACPAgent != "" {
		parts := splitCommand(cfg.ACPAgent)
		acpProvider := acp.New(acp.Config{
			ID:      "acp",
			Command: parts[0],
			Args:    parts[1:],
			WorkDir: workspaceDir(),
			Debug:   cfg.ACPDebug,
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
	r.Route("/hashtag", routes.Hashtags(database))
	r.Route("/media", routes.Media(database))
	r.Route("/workspace", routes.Workspace(workspaceDir(), database))
	r.Route("/agent", routes.Agents(agentRegistry, database, broker))

	// Custom action endpoints (fixes #3)
	actions, err := routes.LoadActions(cfg.ConfigPath)
	if err != nil {
		slog.Warn("failed to load custom actions", "path", cfg.ConfigPath, "error", err)
		actions = &routes.ActionsConfig{Endpoints: map[string]routes.ActionDef{}}
	}
	if len(actions.Endpoints) > 0 {
		// Mount action routes directly (not as subrouter) to avoid chi path conflict
		for actionID := range actions.Endpoints {
			_ = actionID // actions are dispatched by the handler
		}
		r.Post("/agent/{agent_id}/action/{action_id}", routes.TriggerAction(actions, agentRegistry, database, broker))
	}
	r.Get("/agent/commands", routes.GetCommands())

	// Link preview endpoint (fixes #10)
	r.Post("/link-preview", func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			URL string `json:"url"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.URL == "" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(map[string]string{"error": "url is required"})
			return
		}
		preview, err := routes.FetchLinkPreview(req.URL)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadGateway)
			json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(preview)
	})
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
	if err := app.initializeAgents(ctx); err != nil {
		return err
	}
	defer app.shutdownAgents()
	app.forwardAgentEvents(ctx)

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

func (app *App) initializeAgents(ctx context.Context) error {
	active := app.Agents.Active()
	for _, id := range app.Agents.List() {
		p, err := app.Agents.Get(id)
		if err != nil {
			return err
		}
		if err := p.Initialize(ctx); err != nil {
			if id != active {
				slog.Warn("non-active agent initialization failed", "id", id, "error", err)
				continue
			}
			return fmt.Errorf("initialize agent %s: %w", id, err)
		}
	}
	return nil
}

func (app *App) shutdownAgents() {
	for _, id := range app.Agents.List() {
		p, err := app.Agents.Get(id)
		if err != nil {
			continue
		}
		if err := p.Shutdown(context.Background()); err != nil {
			slog.Warn("agent shutdown error", "id", id, "error", err)
		}
	}
}

func (app *App) forwardAgentEvents(ctx context.Context) {
	for _, id := range app.Agents.List() {
		p, err := app.Agents.Get(id)
		if err != nil {
			continue
		}
		go func(provider agent.Provider) {
			for {
				select {
				case event, ok := <-provider.Events():
					if !ok {
						return
					}
					app.SSE.Broadcast(sse.Event{
						Type: "agent_" + event.Type,
						Data: event.Data,
					})
				case <-ctx.Done():
					return
				}
			}
		}(p)
	}
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
