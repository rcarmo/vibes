package routes

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"sync"
	"time"

	"github.com/creack/pty"
	"nhooyr.io/websocket"
)

// TerminalHandler returns an HTTP handler that upgrades to WebSocket and
// bridges to a local PTY running the user's shell.
func TerminalHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			slog.Error("terminal websocket accept", "error", err)
			return
		}
		defer conn.Close(websocket.StatusNormalClosure, "closed")

		ctx, cancel := context.WithCancel(r.Context())
		defer cancel()

		shell := os.Getenv("SHELL")
		if shell == "" {
			shell = "/bin/bash"
		}
		if _, err := exec.LookPath(shell); err != nil {
			shell = "/bin/sh"
		}

		cmd := exec.CommandContext(ctx, shell)
		cmd.Env = append(os.Environ(), "TERM=xterm-256color")

		ptmx, err := pty.Start(cmd)
		if err != nil {
			slog.Error("terminal pty start", "error", err)
			conn.Close(websocket.StatusInternalError, err.Error())
			return
		}
		defer ptmx.Close()

		var wg sync.WaitGroup

		// PTY → WebSocket
		wg.Add(1)
		go func() {
			defer wg.Done()
			buf := make([]byte, 4096)
			for {
				n, err := ptmx.Read(buf)
				if err != nil {
					if err != io.EOF {
						slog.Debug("terminal pty read", "error", err)
					}
					cancel()
					return
				}
				if err := conn.Write(ctx, websocket.MessageBinary, buf[:n]); err != nil {
					cancel()
					return
				}
			}
		}()

		// WebSocket → PTY
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				typ, data, err := conn.Read(ctx)
				if err != nil {
					cancel()
					return
				}
				if typ == websocket.MessageText {
					// Handle resize messages: {"type":"resize","cols":80,"rows":24}
					var msg struct {
						Type string `json:"type"`
						Cols uint16 `json:"cols"`
						Rows uint16 `json:"rows"`
					}
					if json.Unmarshal(data, &msg) == nil && msg.Type == "resize" {
						_ = pty.Setsize(ptmx, &pty.Winsize{
							Cols: msg.Cols,
							Rows: msg.Rows,
						})
						continue
					}
					// Regular text input
					if _, err := ptmx.Write(data); err != nil {
						cancel()
						return
					}
				} else {
					if _, err := ptmx.Write(data); err != nil {
						cancel()
						return
					}
				}
			}
		}()

		// Wait for process to exit
		go func() {
			cmd.Wait()
			time.Sleep(100 * time.Millisecond)
			cancel()
		}()

		<-ctx.Done()
		wg.Wait()
	}
}
