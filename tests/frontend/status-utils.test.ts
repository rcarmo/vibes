import { describe, expect, test } from 'bun:test';
import { describeRateLimit } from '../../static/js/features/agent/status-utils.ts';

describe('agent status utilities', () => {
  test('classifies rate limit messages', () => {
    expect(describeRateLimit('429 too many requests')).toBe('⚠ Rate limited');
    expect(describeRateLimit('tokens per minute exceeded')).toBe('⚠ Rate limited (TPM — tokens per minute)');
    expect(describeRateLimit('RPM quota exceeded')).toBe('⚠ Rate limited (RPM — requests per minute)');
  });

  test('ignores unrelated text', () => {
    expect(describeRateLimit('tool failed')).toBeNull();
    expect(describeRateLimit(null)).toBeNull();
  });
});
