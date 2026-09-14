import { test, expect } from 'bun:test';
import { formatBytes, formatPercent, sparkline } from '../../src/vibes/static/js/components/system-meters.js';

test('meter formatters never coerce missing values to zero', () => {
  for (const value of [null, undefined, NaN, Infinity, -1, '50']) {
    expect(formatBytes(value)).toBe('—'); expect(formatPercent(value)).toBe('—');
  }
  expect(formatPercent(0)).toBe('0%'); expect(formatPercent(101)).toBe('—');
  expect(formatBytes(0)).toBe('0B'); expect(formatBytes(1024 ** 3)).toBe('1.0G');
});
test('sparklines are bounded, percentage-scaled and preserve unavailable gaps', () => {
  expect(sparkline([0, 100], true)).toBe('M 0.00 16.00 L 56.00 0.00');
  expect(sparkline([0, null, 100], true)).toBe('M 0.00 16.00 M 56.00 0.00');
  expect(sparkline([null, undefined])).toBe('');
  expect(sparkline([50], true)).toBe('M 0.00 8.00 L 56 8.00');
  expect(sparkline(Array(90).fill(10)).split(' ').filter(c => c === 'L').length).toBe(29);
});
