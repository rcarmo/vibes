package main

// acp_test.go — quick integration test to verify ACP handshake with all three agents
//
// Run: go run cmd/acp-test/main.go

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"time"
)

type jsonrpcRequest struct {
	JSONRPC string      `json:"jsonrpc"`
	ID      int         `json:"id"`
	Method  string      `json:"method"`
	Params  interface{} `json:"params"`
}

type initParams struct {
	ProtocolVersion    int                    `json:"protocolVersion"`
	ClientInfo         map[string]string      `json:"clientInfo"`
	ClientCapabilities map[string]interface{} `json:"clientCapabilities"`
}

func main() {
	agents := []struct {
		name string
		cmd  string
		args []string
	}{
		{"GitHub Copilot", "copilot-language-server", []string{"--acp", "--stdio"}},
		{"Codex (OpenAI)", "codex-acp", nil},
		{"Claude Agent", "claude-agent-acp", nil},
		{"Pi (via pi-acp)", "pi-acp", nil},
	}

	fmt.Println("=== ACP Handshake Test ===")
	fmt.Println()

	for _, a := range agents {
		fmt.Printf("--- %s (%s) ---\n", a.name, a.cmd)

		// Check binary exists
		path, err := exec.LookPath(a.cmd)
		if err != nil {
			fmt.Printf("  SKIP: %s not found in PATH\n\n", a.cmd)
			continue
		}
		fmt.Printf("  binary: %s\n", path)

		// Spawn agent
		cmd := exec.Command(a.cmd, a.args...)
		cmd.Stderr = io.Discard

		stdin, err := cmd.StdinPipe()
		if err != nil {
			fmt.Printf("  FAIL: stdin pipe: %v\n\n", err)
			continue
		}
		stdout, err := cmd.StdoutPipe()
		if err != nil {
			fmt.Printf("  FAIL: stdout pipe: %v\n\n", err)
			continue
		}

		if err := cmd.Start(); err != nil {
			fmt.Printf("  FAIL: start: %v\n\n", err)
			continue
		}

		// Send initialize request
		initReq := jsonrpcRequest{
			JSONRPC: "2.0",
			ID:      1,
			Method:  "initialize",
			Params: initParams{
				ProtocolVersion:    1,
				ClientInfo:         map[string]string{"name": "vibes-go-test", "version": "0.1.0"},
				ClientCapabilities: map[string]interface{}{},
			},
		}

		reqBytes, _ := json.Marshal(initReq)
		reqBytes = append(reqBytes, '\n')

		_, err = stdin.Write(reqBytes)
		if err != nil {
			fmt.Printf("  FAIL: write: %v\n\n", err)
			cmd.Process.Kill()
			continue
		}

		// Read response with timeout
		done := make(chan string, 1)
		go func() {
			scanner := bufio.NewScanner(stdout)
			if scanner.Scan() {
				done <- scanner.Text()
			} else {
				done <- ""
			}
		}()

		select {
		case line := <-done:
			if line == "" {
				fmt.Printf("  FAIL: empty response\n")
			} else {
				// Parse response
				var resp map[string]interface{}
				if err := json.Unmarshal([]byte(line), &resp); err != nil {
					fmt.Printf("  FAIL: invalid JSON: %v\n", err)
				} else if result, ok := resp["result"].(map[string]interface{}); ok {
					agentInfo := result["agentInfo"].(map[string]interface{})
					name := agentInfo["name"]
					version := agentInfo["version"]

					// Extract capabilities
					caps := result["agentCapabilities"].(map[string]interface{})
					var capList []string
					for k := range caps {
						if k != "_meta" {
							capList = append(capList, k)
						}
					}

					// Auth methods
					authMethods := result["authMethods"]
					var authList []string
					if methods, ok := authMethods.([]interface{}); ok {
						for _, m := range methods {
							if method, ok := m.(map[string]interface{}); ok {
								authList = append(authList, fmt.Sprintf("%v", method["name"]))
							}
						}
					}

					fmt.Printf("  OK: %s v%s\n", name, version)
					fmt.Printf("  protocol: v%v\n", result["protocolVersion"])
					fmt.Printf("  capabilities: %s\n", strings.Join(capList, ", "))
					if len(authList) > 0 {
						fmt.Printf("  auth methods: %s\n", strings.Join(authList, ", "))
					} else {
						fmt.Printf("  auth: pre-configured (env/keyfile)\n")
					}
				} else if errObj, ok := resp["error"]; ok {
					fmt.Printf("  ERROR: %v\n", errObj)
				}
			}

		case <-time.After(5 * time.Second):
			fmt.Printf("  FAIL: timeout (5s)\n")
		}

		stdin.Close()
		cmd.Process.Kill()
		cmd.Wait()
		fmt.Println()
	}

	fmt.Println("=== Done ===")
	os.Exit(0)
}
