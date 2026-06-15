package acp

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWriteTextFileApprovedCreatesFileAndAudits(t *testing.T) {
	root := t.TempDir()
	p, audits := writeTestProvider(root, false, func(req PermissionRequest) (string, error) {
		if req.Method != "fs/write_text_file" || !strings.Contains(req.Title, "write") {
			t.Fatalf("permission request = %#v", req)
		}
		if req.Raw["content"] != nil {
			t.Fatalf("permission request leaked content: %#v", req.Raw)
		}
		return writeTextPermissionAllowOnce, nil
	})
	result, err := p.writeTextFile(map[string]interface{}{"path": "new.txt", "content": "hello"}, "request-1")
	if err != nil {
		t.Fatalf("writeTextFile: %v", err)
	}
	if len(result) != 0 {
		t.Fatalf("result = %#v", result)
	}
	data, err := os.ReadFile(filepath.Join(root, "new.txt"))
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "hello" {
		t.Fatalf("content = %q", data)
	}
	if len(*audits) != 1 || (*audits)[0].Decision != "approved" || (*audits)[0].Bytes != 5 {
		t.Fatalf("audits = %#v", *audits)
	}
}

func TestWriteTextFileDeniedAndTimeoutDoNotMutate(t *testing.T) {
	cases := []struct {
		name     string
		selected string
		reason   string
	}{
		{name: "denied", selected: writeTextPermissionReject, reason: "user_denied"},
		{name: "timeout", selected: "cancelled", reason: "permission_timeout"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			root := t.TempDir()
			p, audits := writeTestProvider(root, false, func(req PermissionRequest) (string, error) {
				return tc.selected, nil
			})
			_, err := p.writeTextFile(map[string]interface{}{"path": "new.txt", "content": "hello"}, "request-1")
			if err == nil || !strings.Contains(err.Error(), tc.reason) {
				t.Fatalf("expected %s error, got %v", tc.reason, err)
			}
			if _, err := os.Stat(filepath.Join(root, "new.txt")); !os.IsNotExist(err) {
				t.Fatalf("file was created after %s: %v", tc.name, err)
			}
			if len(*audits) != 1 || (*audits)[0].Decision == "approved" || (*audits)[0].Reason != tc.reason {
				t.Fatalf("audits = %#v", *audits)
			}
		})
	}
}

func TestWriteTextFileOverwritePolicy(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "existing.txt")
	if err := os.WriteFile(path, []byte("old"), 0o644); err != nil {
		t.Fatal(err)
	}
	p, audits := writeTestProvider(root, false, func(req PermissionRequest) (string, error) {
		return writeTextPermissionAllowOnce, nil
	})
	if _, err := p.writeTextFile(map[string]interface{}{"path": path, "content": "new"}, "request-1"); err == nil {
		t.Fatal("overwrite succeeded without overwrite policy")
	}
	if data, _ := os.ReadFile(path); string(data) != "old" {
		t.Fatalf("content changed without overwrite policy: %q", data)
	}
	if len(*audits) != 1 || (*audits)[0].Decision != "error" || (*audits)[0].Reason != "validation_error" {
		t.Fatalf("audits = %#v", *audits)
	}

	p, audits = writeTestProvider(root, true, func(req PermissionRequest) (string, error) {
		if req.Raw["operation"] != "overwrite" || req.Raw["overwrite"] != true {
			t.Fatalf("overwrite prompt metadata = %#v", req.Raw)
		}
		return writeTextPermissionAllowOnce, nil
	})
	if _, err := p.writeTextFile(map[string]interface{}{"path": path, "content": "new"}, "request-2"); err != nil {
		t.Fatalf("overwrite with policy: %v", err)
	}
	if data, _ := os.ReadFile(path); string(data) != "new" {
		t.Fatalf("content after overwrite = %q", data)
	}
	if len(*audits) != 1 || (*audits)[0].Decision != "approved" {
		t.Fatalf("audits = %#v", *audits)
	}
}

func TestWriteTextFileSymlinkDeniedAndNoMutation(t *testing.T) {
	root := t.TempDir()
	target := filepath.Join(root, "target.txt")
	if err := os.WriteFile(target, []byte("target"), 0o644); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(root, "link.txt")
	if err := os.Symlink(target, link); err != nil {
		t.Skipf("symlink unavailable: %v", err)
	}
	p, audits := writeTestProvider(root, true, func(req PermissionRequest) (string, error) {
		return writeTextPermissionAllowOnce, nil
	})
	if _, err := p.writeTextFile(map[string]interface{}{"path": link, "content": "new"}, "request-1"); err == nil {
		t.Fatal("write through symlink succeeded")
	}
	if data, _ := os.ReadFile(target); string(data) != "target" {
		t.Fatalf("symlink target changed: %q", data)
	}
	if len(*audits) != 1 || (*audits)[0].Decision != "error" {
		t.Fatalf("audits = %#v", *audits)
	}
}

func TestWriteTextFileRevalidationPreventsChangedTarget(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "new.txt")
	p, audits := writeTestProvider(root, false, func(req PermissionRequest) (string, error) {
		if err := os.WriteFile(path, []byte("race"), 0o644); err != nil {
			t.Fatal(err)
		}
		return writeTextPermissionAllowOnce, nil
	})
	if _, err := p.writeTextFile(map[string]interface{}{"path": path, "content": "approved"}, "request-1"); err == nil {
		t.Fatal("write succeeded after target changed")
	}
	if data, _ := os.ReadFile(path); string(data) != "race" {
		t.Fatalf("race file was overwritten: %q", data)
	}
	if len(*audits) != 2 || (*audits)[0].Decision != "approved" || (*audits)[1].Decision != "error" || (*audits)[1].Reason != "revalidation_error" {
		t.Fatalf("audits = %#v", *audits)
	}
}

func TestWriteTextFileDispatcherEnabledAndDisabled(t *testing.T) {
	root := t.TempDir()
	var disabledOut bytes.Buffer
	disabled := New(Config{FSWriteTextEnabled: false, FSWriteRoot: root})
	disabled.writer = &disabledOut
	disabled.handleClientRequest(json.RawMessage(`1`), map[string]json.RawMessage{
		"method": json.RawMessage(strconvQuote("fs/write_text_file")),
		"params": json.RawMessage(`{"path":"new.txt","content":"hello"}`),
	})
	var disabledResp map[string]interface{}
	if err := json.Unmarshal(bytes.TrimSpace(disabledOut.Bytes()), &disabledResp); err != nil {
		t.Fatal(err)
	}
	if code := int(disabledResp["error"].(map[string]interface{})["code"].(float64)); code != -32601 {
		t.Fatalf("disabled code = %d", code)
	}

	var enabledOut bytes.Buffer
	enabled, _ := writeTestProvider(root, false, func(req PermissionRequest) (string, error) {
		return writeTextPermissionAllowOnce, nil
	})
	enabled.writer = &enabledOut
	enabled.handleClientRequest(json.RawMessage(`2`), map[string]json.RawMessage{
		"method": json.RawMessage(strconvQuote("fs/write_text_file")),
		"params": json.RawMessage(`{"path":"new.txt","content":"hello"}`),
	})
	var enabledResp map[string]interface{}
	if err := json.Unmarshal(bytes.TrimSpace(enabledOut.Bytes()), &enabledResp); err != nil {
		t.Fatal(err)
	}
	if _, ok := enabledResp["result"].(map[string]interface{}); !ok {
		t.Fatalf("enabled response = %#v", enabledResp)
	}
	if data, _ := os.ReadFile(filepath.Join(root, "new.txt")); string(data) != "hello" {
		t.Fatalf("dispatcher content = %q", data)
	}
}

func writeTestProvider(root string, allowOverwrite bool, handler PermissionHandler) (*Provider, *[]LocalServiceAuditEvent) {
	p := New(Config{ID: "codex", FSWriteTextEnabled: true, FSWriteRoot: root, FSWriteTextMaxBytes: 1024, FSWriteAllowOverwrite: allowOverwrite})
	p.SetPermissionHandler(handler)
	audits := []LocalServiceAuditEvent{}
	p.SetLocalServiceAuditRecorder(LocalServiceAuditRecorderFunc(func(event LocalServiceAuditEvent) {
		audits = append(audits, event)
	}))
	return p, &audits
}
