package routes

import (
	"fmt"

	"github.com/rcarmo/vibes/internal/agent"
	"github.com/rcarmo/vibes/internal/agent/acp"
)

type acpPermissionProvider interface {
	SetPermissionHandler(acp.PermissionHandler)
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
				return broker.Request(req.ID, req.Method, req.Title, acpOptionsToRouteOptions(req.Options))
			})
		}
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
