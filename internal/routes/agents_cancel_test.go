package routes

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/server/sse"
)

func TestCancelAgentTurnCallsProviderCancel(t *testing.T) {
	registry := agent.NewRegistry()
	stub := &providerRouteStub{id: "pi", status: agent.ProviderStatus{State: "busy", Model: "pi-model"}, events: make(chan agent.Event)}
	registry.RegisterWithDescriptor("pi", stub, agent.ProviderDescriptor{ID: "pi", Label: "Pi", Available: true})

	r := chi.NewRouter()
	r.Post("/agent/{id}/cancel", cancelAgentTurn(registry, sse.NewBroker()))

	req := httptest.NewRequest(http.MethodPost, "/agent/pi/cancel", nil)
	rr := httptest.NewRecorder()
	r.ServeHTTP(rr, req.WithContext(context.Background()))

	if rr.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", rr.Code, rr.Body.String())
	}
	if !stub.canceled {
		t.Fatal("provider Cancel was not called")
	}
}
