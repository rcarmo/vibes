import { describe, expect, test } from 'bun:test';
import { normaliseComposeHistory } from '../../static/js/features/compose/compose-history.ts';

describe('compose history utilities', () => {
  test('deduplicates, trims and filters non-strings', () => {
    expect(normaliseComposeHistory(['  hello  ', '', 'hello', 'world', 123 as unknown as string, ' world '])).toEqual(['hello', 'world']);
  });

  test('handles empty input', () => {
    expect(normaliseComposeHistory(null)).toEqual([]);
    expect(normaliseComposeHistory(undefined)).toEqual([]);
  });
});
