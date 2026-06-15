package db

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestInsertAndGetLocalServiceAudit(t *testing.T) {
	db := tempDB(t)
	metadata := json.RawMessage(`{"source":"acp"}`)
	id, err := db.InsertLocalServiceAudit(LocalServiceAudit{
		Type:       "acp_local_service",
		ProviderID: "copilot",
		SessionID:  "session-1",
		Method:     "fs/write_text_file",
		RequestID:  "request-1",
		Target:     "/workspace/new.txt",
		Decision:   "denied",
		Reason:     "user_denied",
		Bytes:      12,
		Metadata:   metadata,
	})
	if err != nil {
		t.Fatalf("InsertLocalServiceAudit: %v", err)
	}
	got, err := db.GetLocalServiceAudit(id)
	if err != nil {
		t.Fatalf("GetLocalServiceAudit: %v", err)
	}
	if got.Method != "fs/write_text_file" || got.Decision != "denied" || got.Target != "/workspace/new.txt" || got.Bytes != 12 {
		t.Fatalf("audit row = %#v", got)
	}
	if string(got.Metadata) != string(metadata) {
		t.Fatalf("metadata = %s", got.Metadata)
	}
	recent, err := db.GetLocalServiceAudits(10)
	if err != nil {
		t.Fatalf("GetLocalServiceAudits: %v", err)
	}
	if len(recent) != 1 || recent[0].ID != id {
		t.Fatalf("recent = %#v", recent)
	}
}

func TestLocalServiceAuditRequiresMethodAndDecision(t *testing.T) {
	db := tempDB(t)
	if _, err := db.InsertLocalServiceAudit(LocalServiceAudit{Decision: "denied"}); err == nil {
		t.Fatal("expected missing method error")
	}
	if _, err := db.InsertLocalServiceAudit(LocalServiceAudit{Method: "fs/write_text_file"}); err == nil {
		t.Fatal("expected missing decision error")
	}
}

func TestLocalServiceAuditRejectsInvalidMetadata(t *testing.T) {
	db := tempDB(t)
	_, err := db.InsertLocalServiceAudit(LocalServiceAudit{
		Method:   "fs/write_text_file",
		Decision: "denied",
		Metadata: json.RawMessage(`{"unterminated"`),
	})
	if err == nil || !strings.Contains(err.Error(), "metadata") {
		t.Fatalf("expected metadata error, got %v", err)
	}
}
