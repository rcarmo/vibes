import { test, expect } from 'bun:test';
import { SSEClient } from '../../src/vibes/static/js/api.js';

test('named browser file-view events reach application callback', () => {
    const original = globalThis.EventSource;
    const handlers = new Map();
    globalThis.EventSource = class {
        addEventListener(name, handler) { handlers.set(name, handler); }
        close() {}
    };
    const events = [];
    const client = new SSEClient((...event) => events.push(event), () => {});
    try {
        client.connect();
        const payload = { request_id: 'request', session_id: 'chat', path: 'note.md' };
        expect(handlers.has('workspace_view_request')).toBe(true);
        handlers.get('workspace_view_request')({ data: JSON.stringify(payload) });
        expect(events).toEqual([['workspace_view_request', payload]]);
    } finally {
        client.disconnect();
        globalThis.EventSource = original;
    }
});
