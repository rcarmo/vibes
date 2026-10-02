import { test, expect } from 'bun:test';
import { parseTimestamp, formatRelativeTime } from '../../src/vibes/static/js/components/timestamps.js';

test('SQLite UTC, fractions and explicit timezone offsets agree',()=>{
 expect(parseTimestamp('2026-10-02 15:15:48').toISOString()).toBe('2026-10-02T15:15:48.000Z');
 expect(parseTimestamp('2026-10-02 15:15:48.123').toISOString()).toBe('2026-10-02T15:15:48.123Z');
 expect(parseTimestamp('2026-10-02T16:15:48+01:00').getTime()).toBe(parseTimestamp('2026-10-02 15:15:48').getTime());
 expect(parseTimestamp('2026-10-02T11:15:48-04:00').getTime()).toBe(parseTimestamp('2026-10-02 15:15:48').getTime());
});
test('new messages display minutes rather than a false hour',()=>{
 const now=Date.parse('2026-10-02T15:19:03Z');
 expect(formatRelativeTime('2026-10-02 15:18:40',now)).toBe('just now');
 expect(formatRelativeTime('2026-10-02 15:15:48',now)).toBe('3m');
 expect(formatRelativeTime('2026-10-02 14:15:48',now)).toBe('1h');
 expect(formatRelativeTime('2026-10-02T16:15:48+01:00',now)).toBe('3m');
 expect(formatRelativeTime('2026-10-02 15:20:00',now)).toBe('just now');
});
test('relative labels advance with time without changing stored timestamp',()=>{
 const timestamp='2026-10-02 15:00:00';
 expect(formatRelativeTime(timestamp,Date.parse('2026-10-02T15:00:30Z'))).toBe('just now');
 expect(formatRelativeTime(timestamp,Date.parse('2026-10-02T15:01:05Z'))).toBe('1m');
 expect(formatRelativeTime(timestamp,Date.parse('2026-10-02T17:01:05Z'))).toBe('2h');
});
test('invalid and missing timestamps do not become epoch dates',()=>{
 for(const input of ['',null,undefined,123,'not a timestamp'])expect(parseTimestamp(input)).toBeNull();
 expect(formatRelativeTime(null)).toBe('');
 expect(formatRelativeTime('invalid')).toBe('invalid');
});
