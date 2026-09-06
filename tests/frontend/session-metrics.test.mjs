import { test, expect } from 'bun:test';
import { sessionLastMessage, sessionMessageCount } from '../../src/vibes/static/js/components/session-metrics.js';

test('message counts distinguish real zero from missing or invalid data', () => {
    expect(sessionMessageCount(0)).toBe('0 messages');
    expect(sessionMessageCount(1)).toBe('1 message');
    expect(sessionMessageCount(123)).toBe('123 messages');
    for (const value of [null, undefined, '', '0', -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
        expect(sessionMessageCount(value)).toBe('Message count unavailable');
    }
});

test('last message timestamps normalize SQLite UTC and reject missing values', () => {
    expect(sessionLastMessage('2026-09-06 12:30:00').datetime).toBe('2026-09-06T12:30:00.000Z');
    expect(sessionLastMessage('2026-09-06T13:30:00+01:00').datetime).toBe('2026-09-06T12:30:00.000Z');
    for (const value of [null, undefined, '', 'not a timestamp', 123]) expect(sessionLastMessage(value)).toBe(null);
});
