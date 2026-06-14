package routes

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/db"
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
	resp, handled := HandleSlashCommand("/commands", SlashCommandEnv{Registry: registry})
	if !handled {
		t.Fatal("/commands was not handled")
	}
	if resp == nil || resp.Message == "" {
		t.Fatal("/commands returned empty response")
	}
	if !startsWith(resp.Message, "**Available") {
		t.Errorf("unexpected response: %s", resp.Message[:50])
	}
}

func TestHandleSlashCommandAbort(t *testing.T) {
	registry := agent.NewRegistry()
	resp, handled := HandleSlashCommand("/abort", SlashCommandEnv{Registry: registry})
	if !handled {
		t.Fatal("/abort was not handled")
	}
	if resp == nil || resp.Message != "Request cancelled." {
		t.Errorf("unexpected response: %#v", resp)
	}
}

func TestHandleSlashCommandClear(t *testing.T) {
	registry := agent.NewRegistry()
	resp, handled := HandleSlashCommand("/clear", SlashCommandEnv{Registry: registry})
	if !handled {
		t.Fatal("/clear was not handled")
	}
	if resp == nil || resp.Action != "clear" {
		t.Errorf("unexpected response: %#v", resp)
	}
}

func TestHandleSlashCommandNotSlash(t *testing.T) {
	registry := agent.NewRegistry()
	_, handled := HandleSlashCommand("hello", SlashCommandEnv{Registry: registry})
	if handled {
		t.Error("non-slash message was incorrectly handled")
	}
}

func TestHandleSlashCommandShellEmpty(t *testing.T) {
	registry := agent.NewRegistry()
	resp, handled := HandleSlashCommand("/shell", SlashCommandEnv{Registry: registry})
	if !handled {
		t.Fatal("/shell was not handled")
	}
	if resp == nil || resp.Message == "" {
		t.Fatal("/shell returned empty")
	}
}

func TestHandleSlashCommandUserGitHub(t *testing.T) {
	database, err := db.Open(t.TempDir() + "/test.db")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()

	origBase := githubAPIBaseURL
	origClient := githubHTTPClient
	defer func() {
		githubAPIBaseURL = origBase
		githubHTTPClient = origClient
	}()

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/users/rcarmo" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"login":"rcarmo","name":"Rui Carmo","avatar_url":"https://avatars.example/rcarmo.png"}`))
	}))
	defer ts.Close()

	githubAPIBaseURL = ts.URL
	githubHTTPClient = ts.Client()

	resp, handled := HandleSlashCommand("/user-github rcarmo", SlashCommandEnv{DB: database})
	if !handled {
		t.Fatal("/user-github was not handled")
	}
	if resp == nil {
		t.Fatal("/user-github returned nil response")
	}
	if resp.UserName != "Rui Carmo" {
		t.Fatalf("unexpected user name: %q", resp.UserName)
	}
	if resp.UserAvatar != "https://avatars.example/rcarmo.png" {
		t.Fatalf("unexpected avatar: %q", resp.UserAvatar)
	}

	profile, err := database.GetUserProfile()
	if err != nil {
		t.Fatalf("GetUserProfile: %v", err)
	}
	if profile.Name != "Rui Carmo" {
		t.Fatalf("stored name = %q", profile.Name)
	}
	if profile.AvatarURL != "https://avatars.example/rcarmo.png" {
		t.Fatalf("stored avatar = %q", profile.AvatarURL)
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
