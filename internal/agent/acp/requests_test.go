package acp

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

func TestUnsafeClientServiceRequestsRemainUnimplemented(t *testing.T) {
	methods := []string{"fs/write_text_file", "terminal/create", "terminal/output", "terminal/kill"}
	for _, method := range methods {
		t.Run(method, func(t *testing.T) {
			var out bytes.Buffer
			p := New(Config{FSReadTextEnabled: true})
			p.writer = &out
			p.handleClientRequest(json.RawMessage(`1`), map[string]json.RawMessage{
				"method": json.RawMessage(strconvQuote(method)),
				"params": json.RawMessage(`{}`),
			})

			var resp map[string]interface{}
			if err := json.Unmarshal(bytes.TrimSpace(out.Bytes()), &resp); err != nil {
				t.Fatalf("response decode: %v; raw=%q", err, out.String())
			}
			errObj, ok := resp["error"].(map[string]interface{})
			if !ok {
				t.Fatalf("expected error response, got %#v", resp)
			}
			if code := int(errObj["code"].(float64)); code != -32601 {
				t.Fatalf("code = %d", code)
			}
			if msg := errObj["message"].(string); !strings.Contains(msg, "not implemented") {
				t.Fatalf("message = %q", msg)
			}
		})
	}
}

func TestClientCapabilitiesKeepWriteAndTerminalDisabled(t *testing.T) {
	p := New(Config{FSReadTextEnabled: true, FSWriteTextEnabled: true, FSWriteAllowOverwrite: true})
	caps := p.clientCapabilities()
	fsCaps := caps["fs"].(map[string]interface{})
	if fsCaps["writeTextFile"].(bool) {
		t.Fatal("writeTextFile capability must remain disabled")
	}
	if caps["terminal"].(bool) {
		t.Fatal("terminal capability must remain disabled")
	}
	providerCaps := p.Capabilities()
	if providerCaps.FSWriteTextFile || providerCaps.TerminalServices {
		t.Fatalf("provider capabilities expose unsafe services: %#v", providerCaps)
	}
}

func strconvQuote(s string) []byte {
	b, _ := json.Marshal(s)
	return b
}
