package acp

import (
	"crypto/sha256"
	"encoding/hex"
	"strconv"
	"strings"
)

const (
	writeTextPermissionAllowOnce = "allow_once"
	writeTextPermissionReject    = "reject"
	writeTextPreviewMaxRunes     = 160
)

// LocalServiceAuditRecorder receives structured local-service audit events.
// Persistence/UI fanout is deliberately outside the ACP provider for now.
type LocalServiceAuditRecorder interface {
	RecordLocalServiceAudit(LocalServiceAuditEvent)
}

// LocalServiceAuditRecorderFunc adapts a function to LocalServiceAuditRecorder.
type LocalServiceAuditRecorderFunc func(LocalServiceAuditEvent)

func (f LocalServiceAuditRecorderFunc) RecordLocalServiceAudit(event LocalServiceAuditEvent) {
	f(event)
}

// SetLocalServiceAuditRecorder installs an optional audit recorder for future
// ACP local services. nil keeps the current no-op behavior.
func (p *Provider) SetLocalServiceAuditRecorder(recorder LocalServiceAuditRecorder) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.localServiceAuditRecorder = recorder
}

func (p *Provider) recordLocalServiceAudit(event LocalServiceAuditEvent) {
	p.mu.RLock()
	recorder := p.localServiceAuditRecorder
	p.mu.RUnlock()
	if recorder != nil {
		recorder.RecordLocalServiceAudit(event)
	}
}

// WriteTextPermissionDecision is the non-mutating result of a future write
// permission mediation step.
type WriteTextPermissionDecision struct {
	Allowed        bool
	SelectedOption string
	Reason         string
	AuditEvent     LocalServiceAuditEvent
}

func writeTextPermissionRequest(providerID, sessionID, requestID string, plan WriteTextPlan, content string) PermissionRequest {
	operation := "create"
	titleAction := "write"
	if plan.Overwrite {
		operation = "overwrite"
		titleAction = "overwrite"
	}
	preview, truncated := contentPreview(content, writeTextPreviewMaxRunes)
	return PermissionRequest{
		ID:     requestID,
		Method: "fs/write_text_file",
		Title:  "Allow ACP " + titleAction + " of " + plan.ResolvedPath + "?",
		Options: []PermissionOption{
			{ID: writeTextPermissionAllowOnce, Name: "Allow once", Kind: "allow_once"},
			{ID: writeTextPermissionReject, Name: "Reject", Kind: "reject"},
		},
		Raw: map[string]interface{}{
			"type":             "acp_local_service_permission",
			"providerId":       providerID,
			"sessionId":        sessionID,
			"requestId":        requestID,
			"method":           "fs/write_text_file",
			"operation":        operation,
			"target":           plan.ResolvedPath,
			"root":             plan.Root,
			"bytes":            plan.Bytes,
			"overwrite":        plan.Overwrite,
			"exists":           plan.Exists,
			"contentPreview":   preview,
			"previewTruncated": truncated,
			"contentSha256":    contentSHA256(content),
		},
	}
}

func resolveWriteTextPermissionDecision(providerID, sessionID, requestID string, plan WriteTextPlan, selected string, err error) WriteTextPermissionDecision {
	decision := WriteTextPermissionDecision{SelectedOption: selected}
	auditDecision := "denied"
	reason := "user_denied"
	if err != nil {
		auditDecision = "error"
		reason = "permission_error"
	} else {
		switch selected {
		case writeTextPermissionAllowOnce:
			decision.Allowed = true
			auditDecision = "approved"
			reason = "user_approved"
		case "", "cancelled":
			auditDecision = "timeout"
			reason = "permission_timeout"
		case writeTextPermissionReject:
			auditDecision = "denied"
			reason = "user_denied"
		default:
			auditDecision = "denied"
			reason = "invalid_permission_option"
		}
	}
	decision.Reason = reason
	decision.AuditEvent = writePlanAuditEvent(providerID, sessionID, requestID, plan, auditDecision, reason)
	return decision
}

func contentPreview(content string, maxRunes int) (string, bool) {
	if maxRunes <= 0 {
		return "", content != ""
	}
	var b strings.Builder
	count := 0
	truncated := false
	for _, r := range content {
		if count >= maxRunes {
			truncated = true
			break
		}
		b.WriteString(strconv.QuoteRuneToASCII(r))
		count++
	}
	return b.String(), truncated
}

func contentSHA256(content string) string {
	sum := sha256.Sum256([]byte(content))
	return hex.EncodeToString(sum[:])
}
