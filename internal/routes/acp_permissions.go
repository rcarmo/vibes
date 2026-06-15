package routes

import (
	"encoding/json"
	"fmt"
	"log/slog"

	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/agent/acp"
	"github.com/rcarmo/vibes/internal/db"
	"github.com/rcarmo/vibes/internal/server/sse"
)

type acpPermissionProvider interface {
	SetPermissionHandler(acp.PermissionHandler)
}

type acpLocalServiceAuditProvider interface {
	SetLocalServiceAuditRecorder(acp.LocalServiceAuditRecorder)
}

func wireACPPermissionHandlers(registry *agent.Registry, broker *PermissionBroker) {
	if registry == nil || broker == nil {
		return
	}
	for _, id := range registry.List() {
		provider, err := registry.Get(id)
		if err != nil {
			continue
		}
		if p, ok := provider.(acpPermissionProvider); ok {
			p.SetPermissionHandler(func(req acp.PermissionRequest) (string, error) {
				options := acpOptionsToRouteOptions(req.Options)
				if isACPLocalServicePermission(req) {
					return broker.RequestManual(req.ID, req.Method, req.Title, options)
				}
				return broker.Request(req.ID, req.Method, req.Title, options)
			})
		}
		if p, ok := provider.(acpLocalServiceAuditProvider); ok {
			p.SetLocalServiceAuditRecorder(acp.LocalServiceAuditRecorderFunc(func(event acp.LocalServiceAuditEvent) {
				broadcastLocalServiceAudit(broker, event)
			}))
		}
	}
}

func isACPLocalServicePermission(req acp.PermissionRequest) bool {
	if req.Raw == nil {
		return false
	}
	return req.Raw["type"] == "acp_local_service_permission"
}

func broadcastLocalServiceAudit(broker *PermissionBroker, event acp.LocalServiceAuditEvent) {
	if broker == nil {
		return
	}
	if broker.whitelistDB != nil {
		if _, err := broker.whitelistDB.InsertLocalServiceAudit(localServiceAuditFromACP(event)); err != nil {
			slog.Warn("persist local service audit", "error", err, "method", event.Method, "decision", event.Decision)
		}
	}
	if broker.sseBrk == nil {
		return
	}
	broker.sseBrk.Broadcast(sse.Event{Type: "agent_audit", Data: event})
}

func localServiceAuditFromACP(event acp.LocalServiceAuditEvent) db.LocalServiceAudit {
	metadata, _ := json.Marshal(map[string]interface{}{
		"source": "acp",
	})
	return db.LocalServiceAudit{
		Type:       event.Type,
		ProviderID: event.ProviderID,
		SessionID:  event.SessionID,
		Method:     event.Method,
		RequestID:  event.RequestID,
		Target:     event.Target,
		Decision:   event.Decision,
		Reason:     event.Reason,
		Bytes:      event.Bytes,
		Metadata:   metadata,
	}
}

func acpOptionsToRouteOptions(options []acp.PermissionOption) []Option {
	if len(options) == 0 {
		return []Option{{ID: "reject", Label: "Reject"}}
	}
	out := make([]Option, 0, len(options))
	for _, option := range options {
		label := option.Name
		if label == "" {
			label = option.ID
		}
		if option.Kind != "" {
			label = fmt.Sprintf("%s (%s)", label, option.Kind)
		}
		out = append(out, Option{ID: option.ID, Label: label})
	}
	return out
}
