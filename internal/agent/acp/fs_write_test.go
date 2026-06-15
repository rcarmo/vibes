package acp

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPlanWriteTextFileDisabled(t *testing.T) {
	p := New(Config{})
	if _, err := p.planWriteTextFile(map[string]interface{}{"path": "new.txt", "content": "hello"}); err == nil {
		t.Fatal("write plan succeeded while disabled")
	}
}

func TestPlanWriteTextFileInvalidRootFailsClosed(t *testing.T) {
	p := New(Config{FSWriteTextEnabled: true, FSWriteRoot: filepath.Join(t.TempDir(), "missing")})
	if _, err := p.planWriteTextFile(map[string]interface{}{"path": "new.txt", "content": "hello"}); err == nil {
		t.Fatal("write plan succeeded with invalid root")
	}
}

func TestPlanWriteTextFileRejectsTraversalAndSymlinkEscapes(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	if err := os.WriteFile(filepath.Join(outside, "secret.txt"), []byte("secret"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(root, "outside-link")); err != nil {
		t.Skipf("symlink unavailable: %v", err)
	}

	p := New(Config{FSWriteTextEnabled: true, FSWriteRoot: root, FSWriteTextMaxBytes: 1024})
	for _, path := range []string{filepath.Join(outside, "secret.txt"), "../escape.txt", filepath.Join("outside-link", "created.txt")} {
		t.Run(path, func(t *testing.T) {
			if _, err := p.planWriteTextFile(map[string]interface{}{"path": path, "content": "hello"}); err == nil {
				t.Fatalf("write plan allowed escape path %q", path)
			}
		})
	}
}

func TestPlanWriteTextFileRejectsDirectoryFinalSymlinkOversizeAndOverwrite(t *testing.T) {
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, "dir"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "existing.txt"), []byte("old"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "target.txt"), []byte("target"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(root, "target.txt"), filepath.Join(root, "link.txt")); err != nil {
		t.Skipf("symlink unavailable: %v", err)
	}

	p := New(Config{FSWriteTextEnabled: true, FSWriteRoot: root, FSWriteTextMaxBytes: 4})
	cases := []struct {
		name    string
		path    string
		content string
	}{
		{name: "directory", path: filepath.Join(root, "dir"), content: "ok"},
		{name: "final symlink", path: filepath.Join(root, "link.txt"), content: "ok"},
		{name: "oversize", path: filepath.Join(root, "new.txt"), content: "12345"},
		{name: "overwrite denied", path: filepath.Join(root, "existing.txt"), content: "ok"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := p.planWriteTextFile(map[string]interface{}{"path": tc.path, "content": tc.content}); err == nil {
				t.Fatalf("write plan allowed %s", tc.name)
			}
		})
	}
}

func TestPlanWriteTextFileAllowsNewFileAndExplicitOverwrite(t *testing.T) {
	root := t.TempDir()
	existing := filepath.Join(root, "existing.txt")
	if err := os.WriteFile(existing, []byte("old"), 0o644); err != nil {
		t.Fatal(err)
	}
	p := New(Config{FSWriteTextEnabled: true, FSWriteRoot: root, FSWriteTextMaxBytes: 1024, FSWriteAllowOverwrite: true})
	newPlan, err := p.planWriteTextFile(map[string]interface{}{"path": "nested/new.txt", "content": "hello"})
	if err == nil {
		t.Fatalf("write plan should require existing parent directories before future mkdir policy exists: %#v", newPlan)
	}
	newPlan, err = p.planWriteTextFile(map[string]interface{}{"path": "new.txt", "content": "hello"})
	if err != nil {
		t.Fatalf("new file plan failed: %v", err)
	}
	if newPlan.Exists || newPlan.Overwrite || newPlan.Bytes != 5 || !strings.HasPrefix(newPlan.ResolvedPath, root) {
		t.Fatalf("unexpected new file plan: %#v", newPlan)
	}
	overwritePlan, err := p.planWriteTextFile(map[string]interface{}{"path": existing, "content": "hello"})
	if err != nil {
		t.Fatalf("overwrite plan failed: %v", err)
	}
	if !overwritePlan.Exists || !overwritePlan.Overwrite {
		t.Fatalf("unexpected overwrite plan: %#v", overwritePlan)
	}
}

func TestWritePlanAuditEventShape(t *testing.T) {
	plan := WriteTextPlan{ResolvedPath: "/workspace/new.txt", Bytes: 12}
	event := writePlanAuditEvent("copilot", "session-1", "request-1", plan, "denied", "user_denied")
	data, err := json.Marshal(event)
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]interface{}
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded["type"] != "acp_local_service" || decoded["method"] != "fs/write_text_file" || decoded["decision"] != "denied" || decoded["reason"] != "user_denied" {
		t.Fatalf("unexpected audit event: %#v", decoded)
	}
	if decoded["content"] != nil || decoded["environment"] != nil {
		t.Fatalf("audit event leaked payload-like fields: %s", string(data))
	}
}
