// Collapsed drafts receive preview/append events; expanded drafts receive the
// dedicated delta stream. Never consume both copies of the same chunk.
export function applyDraftEvent(current, eventType, data, expanded) {
    if (eventType === 'agent_draft_delta') {
        if (!expanded) return null;
        return (data?.reset ? '' : current) + (typeof data?.delta === 'string' ? data.delta : '');
    }
    if (eventType !== 'agent_draft' || expanded) return null;
    const text = typeof data?.text === 'string' ? data.text : '';
    // Pi emits replacement previews; Copilot/ACP emit explicit append chunks.
    // Legacy events without a mode are snapshots, preserving prior behavior.
    return data?.mode === 'append' ? current + text : text;
}
