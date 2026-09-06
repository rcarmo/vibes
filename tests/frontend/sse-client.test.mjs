import { test, expect } from 'bun:test';
import { SSEClient } from '../../src/vibes/static/js/api.js';

test('SSE transport forwards session and queue notifications with intact payloads', () => {
    const original = globalThis.EventSource;
    class Source extends EventTarget {
        close() { this.closed = true; }
    }
    globalThis.EventSource = Source;
    const received = [];
    const client = new SSEClient((type, data) => received.push({ type, data }), () => {});
    try {
        client.connect();
        const source = client.eventSource;
        for (const type of ['sessions_changed', 'session_model_changed', 'agent_queue_reordered',
            'agent_followup_queued', 'agent_followup_consumed', 'agent_followup_removed', 'agent_steer_queued']) {
            const data = { session_id: 'other', ids: [2, 1] };
            source.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(data) }));
            expect(received.at(-1)).toEqual({ type, data });
        }
        expect(received).toHaveLength(7);
        client.disconnect();
        expect(source.closed).toBe(true);
        expect(client.eventSource).toBe(null);
    } finally {
        client.disconnect();
        if (original === undefined) delete globalThis.EventSource;
        else globalThis.EventSource = original;
    }
});
