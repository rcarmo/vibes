package acp

import (
	"io"
	"log/slog"
	"sync"
)

// debugWriter wraps an io.Writer and logs all writes at debug level. (fixes #11)
type debugWriter struct {
	inner io.WriteCloser
	label string
	mu    sync.Mutex
}

func newDebugWriter(inner io.WriteCloser, label string) *debugWriter {
	return &debugWriter{inner: inner, label: label}
}

func (dw *debugWriter) Write(p []byte) (int, error) {
	dw.mu.Lock()
	defer dw.mu.Unlock()

	// Truncate long messages for logging
	msg := string(p)
	if len(msg) > 500 {
		msg = msg[:500] + "..."
	}
	slog.Debug("ACP wire", "dir", dw.label, "data", msg)
	return dw.inner.Write(p)
}

func (dw *debugWriter) Close() error {
	return dw.inner.Close()
}

// debugReader wraps an io.Reader and logs all reads at debug level.
type debugReader struct {
	inner io.Reader
	label string
}

func newDebugReader(inner io.Reader, label string) *debugReader {
	return &debugReader{inner: inner, label: label}
}

func (dr *debugReader) Read(p []byte) (int, error) {
	n, err := dr.inner.Read(p)
	if n > 0 {
		msg := string(p[:n])
		if len(msg) > 500 {
			msg = msg[:500] + "..."
		}
		slog.Debug("ACP wire", "dir", dr.label, "data", msg)
	}
	return n, err
}
