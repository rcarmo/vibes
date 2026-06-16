package mcpadapter

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
)

const AdapterVersion = "v0.1.0-stub"

// Server is the future bundled stdio MCP adapter. For this scaffolding pass it
// intentionally serves only capability/registry metadata and returns a clear
// not-implemented error for actual protocol serving.
type Server struct {
	Registry Registry
	Env      Environment
	In       io.Reader
	Out      io.Writer
	Err      io.Writer
}

// NewServer constructs a Vibes MCP adapter server with conservative dynamic
// discovery defaults. Future passes should inject app dependencies (DB,
// provider registry, workspace root, SSE UI bridge) through this struct rather
// than importing app packages into internal/mcpadapter.
func NewServer(in io.Reader, out io.Writer, errOut io.Writer) *Server {
	return &Server{
		Registry: NewRegistry(),
		Env:      DefaultEnvironment(),
		In:       in,
		Out:      out,
		Err:      errOut,
	}
}

// Capabilities returns adapter metadata and the currently discoverable tools.
// This is deliberately JSON-serializable so both tests and the future MCP
// initialize/tools-list handlers can reuse it.
func (s *Server) Capabilities() map[string]interface{} {
	return map[string]interface{}{
		"name":              "vibes",
		"version":           AdapterVersion,
		"dynamic_discovery": true,
		"context_strategy":  "metadata-first, bounded slices, stable ids/hashes before content",
		"tools":             s.Registry.Discover(s.Env),
		"all_tools":         s.Registry.All(),
	}
}

// ServeStdio is the future MCP stdio loop. It is intentionally a stub so the
// binary can expose `vibes mcp --stdio` without pretending MCP protocol support
// is complete. Next pass: wire JSON-RPC initialize, tools/list and tools/call
// using Registry.Discover/HandlerFor.
func (s *Server) ServeStdio(ctx context.Context) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}
	if s.Err != nil {
		_, _ = fmt.Fprintln(s.Err, "vibes MCP adapter stdio protocol is scaffolded but not implemented yet")
		encoded, _ := json.MarshalIndent(s.Capabilities(), "", "  ")
		_, _ = fmt.Fprintln(s.Err, string(encoded))
	}
	return ErrToolNotImplemented
}
