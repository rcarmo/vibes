package agent

import "context"

// PromptResourceLink is an explicit resource reference supplied by the user/UI.
// It is metadata only; providers must not read local files implicitly from it.
type PromptResourceLink struct {
	URI      string `json:"uri"`
	Name     string `json:"name,omitempty"`
	MimeType string `json:"mime_type,omitempty"`
}

// PromptRequest is the provider-neutral prompt envelope used for richer ACP
// prompt content while preserving the legacy text-only Prompt method.
type PromptRequest struct {
	Text          string
	ThreadID      int64
	ResourceLinks []PromptResourceLink
}

// RichPromptProvider can handle prompt envelopes with explicit context blocks.
type RichPromptProvider interface {
	PromptRequest(ctx context.Context, req PromptRequest) error
}
