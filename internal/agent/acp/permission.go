package acp

import (
	"errors"
	"fmt"
)

// PermissionOption mirrors the ACP permission option fields Vibes needs to
// present through its existing permission broker.
type PermissionOption struct {
	ID   string
	Name string
	Kind string
}

// PermissionRequest is the provider-neutral subset of an ACP
// session/request_permission request used by the app-level broker adapter.
type PermissionRequest struct {
	ID      string
	Method  string
	Title   string
	Options []PermissionOption
	Raw     map[string]interface{}
}

// PermissionHandler mediates ACP permission requests through the host app.
type PermissionHandler func(PermissionRequest) (string, error)

// SetPermissionHandler installs the app-level permission mediator.
func (p *Provider) SetPermissionHandler(handler PermissionHandler) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.permissionHandler = handler
}

func (p *Provider) requestPermission(params map[string]interface{}) (map[string]interface{}, error) {
	handler := p.getPermissionHandler()
	if handler == nil {
		return nil, errors.New("session/request_permission is unavailable")
	}
	req := parsePermissionRequest(params)
	if len(req.Options) == 0 {
		return nil, errors.New("permission request has no options")
	}
	selected, err := handler(req)
	if err != nil {
		return map[string]interface{}{
			"outcome": map[string]interface{}{"outcome": "cancelled"},
		}, err
	}
	if selected == "" {
		return map[string]interface{}{
			"outcome": map[string]interface{}{"outcome": "cancelled"},
		}, nil
	}
	return map[string]interface{}{
		"outcome": map[string]interface{}{
			"outcome":  "selected",
			"optionId": selected,
		},
	}, nil
}

func (p *Provider) getPermissionHandler() PermissionHandler {
	p.mu.RLock()
	defer p.mu.RUnlock()
	return p.permissionHandler
}

func parsePermissionRequest(params map[string]interface{}) PermissionRequest {
	req := PermissionRequest{Raw: params}
	if toolCall, ok := params["toolCall"].(map[string]interface{}); ok {
		if id, ok := toolCall["toolCallId"].(string); ok {
			req.ID = id
		}
		if title, ok := toolCall["title"].(string); ok {
			req.Title = title
		}
		if kind, ok := toolCall["kind"].(string); ok {
			req.Method = kind
		}
		if req.Method == "" {
			req.Method = permissionStringField(toolCall, "name")
		}
	}
	if req.ID == "" {
		req.ID = permissionStringField(params, "sessionId")
	}
	if req.Method == "" {
		req.Method = "acp/session/request_permission"
	}
	if req.Title == "" {
		req.Title = fmt.Sprintf("Allow %s?", req.Method)
	}
	if opts, ok := params["options"].([]interface{}); ok {
		for _, opt := range opts {
			m, ok := opt.(map[string]interface{})
			if !ok {
				continue
			}
			id := permissionStringField(m, "optionId")
			if id == "" {
				continue
			}
			name := permissionStringField(m, "name")
			if name == "" {
				name = id
			}
			req.Options = append(req.Options, PermissionOption{
				ID:   id,
				Name: name,
				Kind: permissionStringField(m, "kind"),
			})
		}
	}
	if len(req.Options) == 0 {
		req.Options = []PermissionOption{{ID: "reject", Name: "Reject", Kind: "reject"}}
	}
	return req
}

func permissionStringField(m map[string]interface{}, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}
