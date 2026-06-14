package acp

import (
	"os"
	"path/filepath"
	"testing"
)

func TestClientCapabilitiesAdvertiseReadTextOnlyWhenEnabled(t *testing.T) {
	disabled := New(Config{})
	fsCaps := disabled.clientCapabilities()["fs"].(map[string]interface{})
	if fsCaps["readTextFile"].(bool) || fsCaps["writeTextFile"].(bool) {
		t.Fatalf("disabled fs caps = %#v", fsCaps)
	}

	enabled := New(Config{FSReadTextEnabled: true})
	fsCaps = enabled.clientCapabilities()["fs"].(map[string]interface{})
	if !fsCaps["readTextFile"].(bool) || fsCaps["writeTextFile"].(bool) {
		t.Fatalf("enabled fs caps = %#v", fsCaps)
	}
}

func TestReadTextFileDisabled(t *testing.T) {
	p := New(Config{})
	if _, err := p.readTextFile(map[string]interface{}{"path": "README.md"}); err == nil {
		t.Fatal("readTextFile succeeded while disabled")
	}
}

func TestReadTextFileConfinedToRoot(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "note.txt"), []byte("one\ntwo\nthree\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(outside, "secret.txt"), []byte("secret"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(outside, "secret.txt"), filepath.Join(root, "link.txt")); err != nil {
		t.Skipf("symlink unavailable: %v", err)
	}

	p := New(Config{FSReadTextEnabled: true, FSRoot: root, FSReadTextMaxBytes: 1024})
	result, err := p.readTextFile(map[string]interface{}{"path": filepath.Join(root, "note.txt"), "line": float64(2), "limit": float64(1)})
	if err != nil {
		t.Fatalf("readTextFile: %v", err)
	}
	if result["content"] != "two" {
		t.Fatalf("content = %#v", result["content"])
	}
	if _, err := p.readTextFile(map[string]interface{}{"path": filepath.Join(outside, "secret.txt")}); err == nil {
		t.Fatal("outside absolute path was allowed")
	}
	if _, err := p.readTextFile(map[string]interface{}{"path": filepath.Join(root, "link.txt")}); err == nil {
		t.Fatal("symlink escape was allowed")
	}
}

func TestReadTextFileMaxBytes(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "large.txt")
	if err := os.WriteFile(path, []byte("abcdef"), 0o644); err != nil {
		t.Fatal(err)
	}
	p := New(Config{FSReadTextEnabled: true, FSRoot: root, FSReadTextMaxBytes: 3})
	if _, err := p.readTextFile(map[string]interface{}{"path": path}); err == nil {
		t.Fatal("oversized file was allowed")
	}
}
