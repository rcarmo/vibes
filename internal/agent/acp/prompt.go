package acp

import (
	"strings"

	"github.com/rcarmo/vibes/internal/agent"
)

func renderPromptBlocks(req agent.PromptRequest) []interface{} {
	blocks := []interface{}{
		map[string]interface{}{"type": "text", "text": req.Text},
	}
	for _, link := range req.ResourceLinks {
		uri := strings.TrimSpace(link.URI)
		if uri == "" {
			continue
		}
		block := map[string]interface{}{
			"type": "resource_link",
			"uri":  uri,
		}
		if link.Name != "" {
			block["name"] = link.Name
		}
		if link.MimeType != "" {
			block["mimeType"] = link.MimeType
		}
		blocks = append(blocks, block)
	}
	return blocks
}
