package acp

import (
	"bufio"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const defaultReadTextMaxBytes int64 = 256 * 1024

func (p *Provider) clientCapabilities() map[string]interface{} {
	return map[string]interface{}{
		"fs": map[string]interface{}{
			"readTextFile":  p.cfg.FSReadTextEnabled,
			"writeTextFile": false,
		},
		"terminal": false,
	}
}

func (p *Provider) readTextFile(params map[string]interface{}) (map[string]interface{}, error) {
	if !p.cfg.FSReadTextEnabled {
		return nil, errors.New("fs/read_text_file is disabled")
	}
	path, _ := params["path"].(string)
	path = strings.TrimSpace(path)
	if path == "" {
		return nil, errors.New("path is required")
	}
	resolved, err := p.resolveReadPath(path)
	if err != nil {
		return nil, err
	}
	info, err := os.Stat(resolved)
	if err != nil {
		return nil, err
	}
	if info.IsDir() {
		return nil, fmt.Errorf("path is a directory")
	}
	maxBytes := p.cfg.FSReadTextMaxBytes
	if maxBytes <= 0 {
		maxBytes = defaultReadTextMaxBytes
	}
	if info.Size() > maxBytes {
		return nil, fmt.Errorf("file is too large (%d bytes > %d bytes)", info.Size(), maxBytes)
	}
	content, err := readTextLines(resolved, intParam(params, "line"), intParam(params, "limit"), maxBytes)
	if err != nil {
		return nil, err
	}
	return map[string]interface{}{"content": content}, nil
}

func (p *Provider) resolveReadPath(path string) (string, error) {
	root := p.cfg.FSRoot
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
	rootEval, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", err
	}
	absPath := path
	if !filepath.IsAbs(absPath) {
		absPath = filepath.Join(rootEval, absPath)
	}
	cleanAbs, err := filepath.Abs(filepath.Clean(absPath))
	if err != nil {
		return "", err
	}
	resolved, err := filepath.EvalSymlinks(cleanAbs)
	if err != nil {
		return "", err
	}
	rel, err := filepath.Rel(rootEval, resolved)
	if err != nil {
		return "", err
	}
	if rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) || filepath.IsAbs(rel) {
		return "", fmt.Errorf("path escapes ACP filesystem root")
	}
	return resolved, nil
}

func readTextLines(path string, line, limit int, maxBytes int64) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	if int64(len(data)) > maxBytes {
		return "", fmt.Errorf("file is too large (%d bytes > %d bytes)", len(data), maxBytes)
	}
	if line <= 0 && limit <= 0 {
		return string(data), nil
	}
	start := line
	if start <= 0 {
		start = 1
	}
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	var out strings.Builder
	current := 0
	written := 0
	for scanner.Scan() {
		current++
		if current < start {
			continue
		}
		if limit > 0 && written >= limit {
			break
		}
		if written > 0 {
			out.WriteByte('\n')
		}
		out.WriteString(scanner.Text())
		written++
	}
	if err := scanner.Err(); err != nil {
		return "", err
	}
	return out.String(), nil
}

func intParam(params map[string]interface{}, key string) int {
	value, ok := params[key]
	if !ok || value == nil {
		return 0
	}
	switch v := value.(type) {
	case float64:
		return int(v)
	case int:
		return v
	}
	return 0
}
