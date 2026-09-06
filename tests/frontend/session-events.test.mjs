import { test, expect } from 'bun:test';
import { eventMatchesSession } from '../../src/vibes/static/js/components/session-events.js';

test('conversation events respect explicit and legacy scope', () => {
    expect(eventMatchesSession('agent_status', { session_id: 'other' }, 'default')).toBe(false);
    expect(eventMatchesSession('new_post', { data: { session_id: 'other' } }, 'other')).toBe(true);
    expect(eventMatchesSession('new_post', { data: {} }, 'default')).toBe(true);
    expect(eventMatchesSession('new_post', { data: {} }, 'other')).toBe(false);
    expect(eventMatchesSession('agent_request', { session_id: 'other' }, 'default')).toBe(false);
    expect(eventMatchesSession('connected', {}, 'other')).toBe(true);
    expect(eventMatchesSession('workspace_update', {}, 'other')).toBe(true);
});
