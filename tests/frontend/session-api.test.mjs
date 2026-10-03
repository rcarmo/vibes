import { test, expect } from 'bun:test';
import { sendAgentMessage, getSessionTimeline, createSession, updateSession, deleteSession } from '../../src/vibes/static/js/api.js';

test('session APIs carry explicit identities and escape path segments', async () => {
    const original = globalThis.fetch;
    const requests = [];
    globalThis.fetch = async (url, options = {}) => {
        requests.push({ url, options });
        return { ok: true, json: async () => ({}) };
    };
    try {
        await sendAgentMessage('default', 'hello', null, [], 'auto', 'other');
        expect(JSON.parse(requests[0].options.body).session_id).toBe('other');
        await getSessionTimeline('chat/other', 5, 9);
        expect(requests[1].url).toBe('/sessions/chat%2Fother/timeline?limit=5&before=9');
        await createSession('New', 'default');
        expect(JSON.parse(requests[2].options.body)).toEqual({ name: 'New', parent_id: 'default' });
        await updateSession('other', { pinned: true });
        expect(requests[3].options.method).toBe('PATCH');
        await deleteSession('other');
        expect(requests[4].options.method).toBe('DELETE');
    } finally { globalThis.fetch = original; }
});

test('rejected admission preserves stored identity without implying retry safety', async () => {
    const original = globalThis.fetch;
    globalThis.fetch = async () => ({ ok: false, status: 503, json: async () => ({ error: 'Unavailable', admitted: false, user_message: { id: 42 }, thread_id: 7 }) });
    try {
        let failure;
        try { await sendAgentMessage('default', 'hello'); } catch (error) { failure = error; }
        expect(failure.status).toBe(503);
        expect(failure.admitted).toBe(false);
        expect(failure.storedMessageId).toBe(42);
        expect(failure.threadId).toBe(7);
    } finally { globalThis.fetch = original; }
});
