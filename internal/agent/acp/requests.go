package acp

import (
	"encoding/json"
	"fmt"
)

func (p *Provider) handleClientRequest(idRaw json.RawMessage, msg map[string]json.RawMessage) {
	var id interface{}
	if err := json.Unmarshal(idRaw, &id); err != nil {
		return
	}
	var method string
	_ = json.Unmarshal(msg["method"], &method)
	var params map[string]interface{}
	if raw, ok := msg["params"]; ok && len(raw) > 0 {
		_ = json.Unmarshal(raw, &params)
	}
	if params == nil {
		params = map[string]interface{}{}
	}

	switch method {
	case "fs/read_text_file":
		result, err := p.readTextFile(params)
		if err != nil {
			p.sendErrorResponse(id, -32000, err.Error())
			return
		}
		p.sendResultResponse(id, result)
	case "fs/write_text_file", "terminal/create", "terminal/output", "terminal/kill", "session/request_permission":
		p.sendErrorResponse(id, -32601, fmt.Sprintf("%s is not implemented by Vibes", method))
	default:
		p.sendErrorResponse(id, -32601, fmt.Sprintf("method not found: %s", method))
	}
}

func (p *Provider) sendResultResponse(id interface{}, result interface{}) {
	resp := map[string]interface{}{
		"jsonrpc": "2.0",
		"id":      id,
		"result":  result,
	}
	p.writeJSON(resp)
}

func (p *Provider) sendErrorResponse(id interface{}, code int, message string) {
	resp := map[string]interface{}{
		"jsonrpc": "2.0",
		"id":      id,
		"error": map[string]interface{}{
			"code":    code,
			"message": message,
		},
	}
	p.writeJSON(resp)
}

func (p *Provider) writeJSON(msg map[string]interface{}) {
	if p.writer == nil {
		return
	}
	data, _ := json.Marshal(msg)
	p.writeMu.Lock()
	defer p.writeMu.Unlock()
	_, _ = p.writer.Write(append(data, '\n'))
}
