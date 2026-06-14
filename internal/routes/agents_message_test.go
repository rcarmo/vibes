package routes

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/db"
	"github.com/rcarmo/vibes/internal/server/sse"
)

func newBackendTestRegistry() *agent.Registry {
	registry := agent.NewRegistry()
	registry.RegisterWithDescriptor("pi", &providerRouteStub{id: "pi", status: agent.ProviderStatus{State: "idle", Model: "pi-model"}, events: make(chan agent.Event)}, agent.ProviderDescriptor{
		ID:        "pi",
		Label:     "Pi",
		Family:    "pi",
		Transport: "pi-rpc",
		Available: true,
	})
	registry.RegisterWithDescriptor("codex", &providerRouteStub{id: "codex", status: agent.ProviderStatus{State: "idle", Model: "codex-model"}, events: make(chan agent.Event)}, agent.ProviderDescriptor{
		ID:        "codex",
		Label:     "Codex",
		Family:    "codex",
		Transport: "acp",
		Available: true,
	})
	return registry
}

func postAgentMessage(t *testing.T, router http.Handler, body map[string]interface{}) map[string]interface{} {
	t.Helper()
	payload, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/agent/default/message", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	router.ServeHTTP(rr, req)
	if rr.Code != http.StatusAccepted {
		t.Fatalf("status = %d, body = %s", rr.Code, rr.Body.String())
	}
	var response map[string]interface{}
	if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
		t.Fatalf("json response: %v", err)
	}
	return response
}

func TestSendAgentMessageStoresRootBackendProvenance(t *testing.T) {
	database, err := db.Open(t.TempDir() + "/test.db")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()

	registry := newBackendTestRegistry()
	router := chi.NewRouter()
	router.Post("/agent/{id}/message", sendAgentMessage(registry, database, sse.NewBroker()))

	response := postAgentMessage(t, router, map[string]interface{}{
		"content":    "hello pi",
		"backend_id": "pi",
	})
	postID := int64(response["id"].(float64))
	threadID := int64(response["thread_id"].(float64))
	if postID != threadID {
		t.Fatalf("root post id %d != thread id %d", postID, threadID)
	}

	interaction, err := database.GetInteraction(postID)
	if err != nil {
		t.Fatalf("GetInteraction: %v", err)
	}
	var payload db.InteractionData
	if err := json.Unmarshal(interaction.Data, &payload); err != nil {
		t.Fatalf("unmarshal interaction: %v", err)
	}
	if payload.Backend == nil {
		t.Fatal("backend metadata missing")
	}
	if payload.Backend.ID != "pi" || payload.Backend.Transport != "pi-rpc" || payload.Backend.Model != "pi-model" {
		t.Fatalf("unexpected backend metadata: %#v", payload.Backend)
	}
	if payload.Backend.ThreadBackendGeneration != 1 {
		t.Fatalf("generation = %d, want 1", payload.Backend.ThreadBackendGeneration)
	}

	threadBackend, err := database.GetThreadBackend(threadID)
	if err != nil {
		t.Fatalf("GetThreadBackend: %v", err)
	}
	if threadBackend == nil || threadBackend.Backend.ID != "pi" || threadBackend.BackendGeneration != 1 {
		t.Fatalf("unexpected thread backend: %#v", threadBackend)
	}
}

func TestSendAgentMessageReplyBackendOverrideRecordsSwitchBeforeMessage(t *testing.T) {
	database, err := db.Open(t.TempDir() + "/test.db")
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer database.Close()

	registry := newBackendTestRegistry()
	if _, _, _, err := switchThreadBackend(database, registry, 100, "pi"); err != nil {
		t.Fatalf("seed thread backend: %v", err)
	}
	router := chi.NewRouter()
	router.Post("/agent/{id}/message", sendAgentMessage(registry, database, sse.NewBroker()))

	response := postAgentMessage(t, router, map[string]interface{}{
		"content":    "switch to codex",
		"thread_id":  float64(100),
		"backend_id": "codex",
	})
	postID := int64(response["id"].(float64))

	interaction, err := database.GetInteraction(postID)
	if err != nil {
		t.Fatalf("GetInteraction: %v", err)
	}
	var payload db.InteractionData
	if err := json.Unmarshal(interaction.Data, &payload); err != nil {
		t.Fatalf("unmarshal interaction: %v", err)
	}
	if payload.Backend == nil || payload.Backend.ID != "codex" || payload.Backend.ThreadBackendGeneration != 2 {
		t.Fatalf("unexpected user message backend: %#v", payload.Backend)
	}

	threadBackend, err := database.GetThreadBackend(100)
	if err != nil {
		t.Fatalf("GetThreadBackend: %v", err)
	}
	if threadBackend == nil || threadBackend.Backend.ID != "codex" || threadBackend.BackendGeneration != 2 {
		t.Fatalf("unexpected thread backend: %#v", threadBackend)
	}

	thread, err := database.GetThread(100)
	if err != nil {
		t.Fatalf("GetThread: %v", err)
	}
	var switchID int64
	for _, item := range thread {
		var data db.InteractionData
		if err := json.Unmarshal(item.Data, &data); err != nil {
			t.Fatalf("unmarshal thread item: %v", err)
		}
		if data.BackendSwitch != nil {
			switchID = item.ID
			if data.BackendSwitch.From != "pi" || data.BackendSwitch.To != "codex" || data.BackendSwitch.ThreadBackendGeneration != 2 {
				t.Fatalf("unexpected switch payload: %#v", data.BackendSwitch)
			}
		}
	}
	if switchID == 0 {
		t.Fatal("backend switch system interaction not found")
	}
	if switchID >= postID {
		t.Fatalf("switch interaction id %d should precede message id %d", switchID, postID)
	}
}
