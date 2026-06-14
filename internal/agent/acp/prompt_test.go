package acp

import (
	"testing"

	"github.com/rcarmo/vibes/internal/agent"
)

func TestRenderPromptBlocksIncludesExplicitResourceLinks(t *testing.T) {
	blocks := renderPromptBlocks(agent.PromptRequest{
		Text: "summarize this",
		ResourceLinks: []agent.PromptResourceLink{
			{URI: "file:///workspace/README.md", Name: "README", MimeType: "text/markdown"},
			{URI: "https://example.test/spec"},
			{URI: "   "},
		},
	})

	if len(blocks) != 3 {
		t.Fatalf("blocks len = %d, want text + 2 resource links: %#v", len(blocks), blocks)
	}
	text, ok := blocks[0].(map[string]interface{})
	if !ok || text["type"] != "text" || text["text"] != "summarize this" {
		t.Fatalf("text block = %#v", blocks[0])
	}
	link, ok := blocks[1].(map[string]interface{})
	if !ok || link["type"] != "resource_link" || link["uri"] != "file:///workspace/README.md" || link["mimeType"] != "text/markdown" {
		t.Fatalf("resource link block = %#v", blocks[1])
	}
	minimal, ok := blocks[2].(map[string]interface{})
	if !ok || minimal["type"] != "resource_link" || minimal["uri"] != "https://example.test/spec" {
		t.Fatalf("minimal resource link block = %#v", blocks[2])
	}
}

func TestRenderPromptBlocksDoesNotInventMediaOrEmbeddedBlocks(t *testing.T) {
	blocks := renderPromptBlocks(agent.PromptRequest{Text: "hello"})
	if len(blocks) != 1 {
		t.Fatalf("blocks = %#v", blocks)
	}
	block := blocks[0].(map[string]interface{})
	if block["type"] != "text" {
		t.Fatalf("block = %#v", block)
	}
}
