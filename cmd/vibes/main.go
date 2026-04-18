package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/rcarmo/vibes/internal/app"
	"github.com/rcarmo/vibes/internal/config"
)

func main() {
	// Load configuration from environment
	cfg, err := config.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "configuration error: %v\n", err)
		os.Exit(1)
	}

	// Set up structured logging
	level := slog.LevelInfo
	if cfg.Debug {
		level = slog.LevelDebug
	}
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: level})))

	// Create application
	application, err := app.New(cfg)
	if err != nil {
		slog.Error("failed to create application", "error", err)
		os.Exit(1)
	}

	// Graceful shutdown on SIGINT/SIGTERM
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	slog.Info("starting vibes",
		"host", cfg.Host,
		"port", cfg.Port,
		"agent", cfg.DefaultAgent,
	)

	if err := application.Run(ctx); err != nil {
		slog.Error("application error", "error", err)
		os.Exit(1)
	}
}
