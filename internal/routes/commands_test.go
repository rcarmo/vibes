package routes

import (
	"testing"

	"github.com/rcarmo/vibes/internal/agent"
)

func TestBuiltinCommands(t *testing.T) {
	cmds := builtinCommands()
	if len(cmds) == 0 {
		t.Fatal("builtinCommands returned empty")
	}

	// All commands should start with /
	for _, cmd := range cmds {
		if cmd.Name[0] != '/' {
			t.Errorf("command %q does not start with /", cmd.Name)
		}
	}
}

func TestHandleSlashCommandCommands(t *testing.T) {
	registry := agent.NewRegistry()
	resp, handled := HandleSlashCommand("/commands", registry)
	if !handled {
		t.Fatal("/commands was not handled")
	}
	if resp == "" {
		t.Fatal("/commands returned empty response")
	}
	if !startsWith(resp, "**Available") {
		t.Errorf("unexpected response: %s", resp[:50])
	}
}

func TestHandleSlashCommandAbort(t *testing.T) {
	registry := agent.NewRegistry()
	resp, handled := HandleSlashCommand("/abort", registry)
	if !handled {
		t.Fatal("/abort was not handled")
	}
	if resp != "Request cancelled." {
		t.Errorf("unexpected response: %q", resp)
	}
}

func TestHandleSlashCommandClear(t *testing.T) {
	registry := agent.NewRegistry()
	resp, handled := HandleSlashCommand("/clear", registry)
	if !handled {
		t.Fatal("/clear was not handled")
	}
	if resp != "[clear]" {
		t.Errorf("unexpected response: %q", resp)
	}
}

func TestHandleSlashCommandNotSlash(t *testing.T) {
	registry := agent.NewRegistry()
	_, handled := HandleSlashCommand("hello", registry)
	if handled {
		t.Error("non-slash message was incorrectly handled")
	}
}

func TestHandleSlashCommandShellEmpty(t *testing.T) {
	registry := agent.NewRegistry()
	resp, handled := HandleSlashCommand("/shell", registry)
	if !handled {
		t.Fatal("/shell was not handled")
	}
	if resp == "" {
		t.Fatal("/shell returned empty")
	}
}

func TestExtractMeta(t *testing.T) {
	html := `<html><head>
		<meta property="og:title" content="Test Title">
		<meta property="og:description" content="Test Description">
		<meta property="og:image" content="https://example.com/img.png">
		<title>Fallback Title</title>
	</head></html>`

	title := extractMeta(html, "og:title")
	if title != "Test Title" {
		t.Errorf("title = %q, want 'Test Title'", title)
	}

	desc := extractMeta(html, "og:description")
	if desc != "Test Description" {
		t.Errorf("description = %q", desc)
	}

	img := extractMeta(html, "og:image")
	if img != "https://example.com/img.png" {
		t.Errorf("image = %q", img)
	}
}

func TestExtractTitle(t *testing.T) {
	html := `<html><head><title>My Page</title></head></html>`
	title := extractTitle(html)
	if title != "My Page" {
		t.Errorf("title = %q, want 'My Page'", title)
	}
}

func TestExtractMetaAltOrder(t *testing.T) {
	// content before property
	html := `<meta content="Alt Title" property="og:title">`
	title := extractMeta(html, "og:title")
	if title != "Alt Title" {
		t.Errorf("alt order title = %q, want 'Alt Title'", title)
	}
}
