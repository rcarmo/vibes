package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/rcarmo/vibes/internal/app"
	"github.com/rcarmo/vibes/internal/config"
	"github.com/rcarmo/vibes/internal/mcpadapter"
)

func main() {
	if len(os.Args) > 1 && os.Args[1] == "mcp" {
		if err := runMCPCommand(os.Args[2:]); err != nil {
			fmt.Fprintf(os.Stderr, "mcp error: %v\n", err)
			os.Exit(1)
		}
		return
	}

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

func runMCPCommand(args []string) error {
	server := mcpadapter.NewServer(os.Stdin, os.Stdout, os.Stderr)
	if len(args) == 0 || args[0] == "--help" || args[0] == "-h" {
		fmt.Fprintln(os.Stdout, "Usage: vibes mcp --list-tools | --stdio")
		fmt.Fprintln(os.Stdout, "")
		fmt.Fprintln(os.Stdout, "The bundled Vibes MCP adapter surface is scaffolded; --stdio protocol serving is not implemented yet.")
		return nil
	}
	for _, arg := range args {
		switch arg {
		case "--list-tools", "list-tools":
			encoded, err := json.MarshalIndent(server.Capabilities(), "", "  ")
			if err != nil {
				return err
			}
			fmt.Fprintln(os.Stdout, string(encoded))
			return nil
		case "--stdio", "stdio":
			ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
			defer cancel()
			err := server.ServeStdio(ctx)
			if errors.Is(err, mcpadapter.ErrToolNotImplemented) {
				return err
			}
			return err
		}
	}
	return fmt.Errorf("unknown mcp arguments: %v", args)
}
