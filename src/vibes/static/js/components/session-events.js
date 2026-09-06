// Global transport/config events are shared; conversation events are not.
const scoped = new Set([
    'session_model_changed', 'new_post', 'new_reply', 'agent_response', 'interaction_updated',
    'agent_status', 'agent_draft', 'agent_draft_delta', 'agent_thought',
    'agent_thought_delta', 'agent_request', 'agent_request_timeout',
]);

export function eventMatchesSession(type, data, sessionId) {
    if (!scoped.has(type)) return true;
    const owner = data?.session_id ?? data?.data?.session_id ?? 'default';
    return owner === sessionId;
}
