// Package vibes is the root package for the Vibes Go binary.
//
// It exists primarily to host the embed directive for the static frontend
// bundle so that the resulting binary is fully self-contained (no runtime
// dependency on a static/ directory on disk).
//
// The build pipeline must run `bun run build.js` before `go build` to
// ensure static/dist/ is up to date.
package vibes

import (
	"embed"
	"io/fs"
	"net/http"
)

//go:embed all:static
var staticFiles embed.FS

// StaticFS returns the embedded static assets as an http.FileSystem rooted
// at the static/ subdirectory.
func StaticFS() (http.FileSystem, error) {
	sub, err := fs.Sub(staticFiles, "static")
	if err != nil {
		return nil, err
	}
	return http.FS(sub), nil
}

// StaticSub returns the embedded static assets as an fs.FS rooted at static/.
func StaticSub() (fs.FS, error) {
	return fs.Sub(staticFiles, "static")
}
