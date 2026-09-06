import { test, expect } from 'bun:test';
import { sessionLastMessage } from '../../src/vibes/static/js/components/session-metrics.js';

test('last message timestamps normalize SQLite UTC and reject missing values', () => {
    expect(sessionLastMessage('2026-09-06 12:30:00').datetime).toBe('2026-09-06T12:30:00.000Z');
    expect(sessionLastMessage('2026-09-06T13:30:00+01:00').datetime).toBe('2026-09-06T12:30:00.000Z');
    for (const value of [null, undefined, '', 'not a timestamp', 123]) expect(sessionLastMessage(value)).toBe(null);
});
