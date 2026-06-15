package acp

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const defaultWriteTextMaxBytes int64 = 256 * 1024

// LocalServiceAuditEvent is the structured audit shape future ACP local
// services should emit. It intentionally excludes full file contents, terminal
// output, raw environment variables, and other secret-bearing payloads.
type LocalServiceAuditEvent struct {
	Type       string `json:"type"`
	ProviderID string `json:"provider_id,omitempty"`
	SessionID  string `json:"session_id,omitempty"`
	Method     string `json:"method"`
	RequestID  string `json:"request_id,omitempty"`
	Target     string `json:"target,omitempty"`
	Decision   string `json:"decision"`
	Reason     string `json:"reason,omitempty"`
	Bytes      int64  `json:"bytes,omitempty"`
	Timestamp  string `json:"timestamp"`
}

// WriteTextPlan is a non-mutating validation result for a future
// fs/write_text_file implementation.
type WriteTextPlan struct {
	RequestedPath string
	Root          string
	ResolvedPath  string
	Parent        string
	Bytes         int64
	Exists        bool
	Overwrite     bool
}

func (p *Provider) planWriteTextFile(params map[string]interface{}) (WriteTextPlan, error) {
	if !p.cfg.FSWriteTextEnabled {
		return WriteTextPlan{}, errors.New("fs/write_text_file is disabled")
	}
	path, _ := params["path"].(string)
	path = strings.TrimSpace(path)
	if path == "" {
		return WriteTextPlan{}, errors.New("path is required")
	}
	if strings.ContainsRune(path, '\x00') {
		return WriteTextPlan{}, errors.New("path contains NUL byte")
	}
	content, _ := params["content"].(string)
	maxBytes := p.cfg.FSWriteTextMaxBytes
	if maxBytes <= 0 {
		maxBytes = defaultWriteTextMaxBytes
	}
	if int64(len([]byte(content))) > maxBytes {
		return WriteTextPlan{}, fmt.Errorf("write payload is too large (%d bytes > %d bytes)", len([]byte(content)), maxBytes)
	}
	root, err := p.resolveWriteRoot()
	if err != nil {
		return WriteTextPlan{}, err
	}
	resolved, parent, exists, err := resolveWriteTarget(root, path)
	if err != nil {
		return WriteTextPlan{}, err
	}
	if exists && !p.cfg.FSWriteAllowOverwrite {
		return WriteTextPlan{}, errors.New("refusing to overwrite existing file")
	}
	return WriteTextPlan{
		RequestedPath: path,
		Root:          root,
		ResolvedPath:  resolved,
		Parent:        parent,
		Bytes:         int64(len([]byte(content))),
		Exists:        exists,
		Overwrite:     exists,
	}, nil
}

func (p *Provider) resolveWriteRoot() (string, error) {
	root := p.cfg.FSWriteRoot
	if root == "" {
		root = p.cfg.FSRoot
	}
	if root == "" {
		root = p.cfg.WorkDir
	}
	if root == "" {
		var err error
		root, err = os.Getwd()
		if err != nil {
			return "", err
		}
	}
	resolved, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", fmt.Errorf("resolve ACP write root: %w", err)
	}
	info, err := os.Stat(resolved)
	if err != nil {
		return "", fmt.Errorf("stat ACP write root: %w", err)
	}
	if !info.IsDir() {
		return "", errors.New("ACP write root is not a directory")
	}
	return resolved, nil
}

func resolveWriteTarget(root, path string) (resolved string, parent string, exists bool, err error) {
	absPath := path
	if !filepath.IsAbs(absPath) {
		absPath = filepath.Join(root, absPath)
	}
	cleanAbs, err := filepath.Abs(filepath.Clean(absPath))
	if err != nil {
		return "", "", false, err
	}
	if cleanAbs == filepath.Clean(root) {
		return "", "", false, errors.New("path points at ACP write root")
	}
	parentClean := filepath.Dir(cleanAbs)
	parentResolved, err := filepath.EvalSymlinks(parentClean)
	if err != nil {
		return "", "", false, fmt.Errorf("resolve write parent: %w", err)
	}
	if err := ensureInsideRoot(root, parentResolved); err != nil {
		return "", "", false, err
	}
	target := filepath.Join(parentResolved, filepath.Base(cleanAbs))
	if err := ensureInsideRoot(root, target); err != nil {
		return "", "", false, err
	}
	info, err := os.Lstat(target)
	if err == nil {
		if info.Mode()&os.ModeSymlink != 0 {
			return "", "", false, errors.New("refusing to write through symlink")
		}
		if info.IsDir() {
			return "", "", false, errors.New("path is a directory")
		}
		return target, parentResolved, true, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return "", "", false, err
	}
	return target, parentResolved, false, nil
}

func ensureInsideRoot(root, target string) error {
	rel, err := filepath.Rel(root, target)
	if err != nil {
		return err
	}
	if rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) || filepath.IsAbs(rel) {
		return errors.New("path escapes ACP filesystem root")
	}
	return nil
}

func writePlanAuditEvent(providerID, sessionID, requestID string, plan WriteTextPlan, decision, reason string) LocalServiceAuditEvent {
	return LocalServiceAuditEvent{
		Type:       "acp_local_service",
		ProviderID: providerID,
		SessionID:  sessionID,
		Method:     "fs/write_text_file",
		RequestID:  requestID,
		Target:     plan.ResolvedPath,
		Decision:   decision,
		Reason:     reason,
		Bytes:      plan.Bytes,
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
	}
}
