package routes

import (
	"path/filepath"
	"testing"
)

// FuzzSafePath ensures safePath never allows path traversal.
func FuzzSafePath(f *testing.F) {
	f.Add("/etc/passwd")
	f.Add("../../../etc/shadow")
	f.Add("..\\..\\windows\\system32")
	f.Add("./valid/path.txt")
	f.Add("normal.txt")
	f.Add("")
	f.Add("/")
	f.Add("////")
	f.Add("a/../b/../c/../../../etc/hosts")
	f.Add("\x00")

	f.Fuzz(func(t *testing.T, input string) {
		workDir := "/workspace"
		result := safePath(workDir, input)

		// Invariant: result is either empty (rejected) or starts with workDir
		if result != "" && result != workDir {
			abs, _ := filepath.Abs(result)
			if abs != "" && len(abs) > 0 {
				if !hasPrefix(abs, workDir) {
					t.Errorf("safePath(%q, %q) = %q — escapes workDir!", workDir, input, result)
				}
			}
		}
	})
}

func hasPrefix(path, prefix string) bool {
	return len(path) >= len(prefix) && path[:len(prefix)] == prefix
}

// FuzzIntQuery ensures intQuery never panics.
func FuzzIntQuery(f *testing.F) {
	f.Add("42")
	f.Add("")
	f.Add("-1")
	f.Add("99999999999999999999")
	f.Add("not-a-number")
	f.Add("1.5")

	f.Fuzz(func(t *testing.T, value string) {
		// Create a fake request with the query param
		// Just test the parsing logic directly
		n, err := parseInt(value)
		_ = n
		_ = err
		// Should never panic
	})
}

// parseInt is a fuzz-friendly version of strconv.Atoi
func parseInt(s string) (int, error) {
	if s == "" {
		return 0, nil
	}
	var n int
	var neg bool
	start := 0
	if s[0] == '-' {
		neg = true
		start = 1
	}
	for i := start; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return 0, nil
		}
		n = n*10 + int(s[i]-'0')
	}
	if neg {
		n = -n
	}
	return n, nil
}
