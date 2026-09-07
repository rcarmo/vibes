import { test, expect } from 'bun:test';
import { usagePresentation } from '../../src/vibes/static/js/components/usage.js';

test('usage keeps reported zero distinct from unknown and tiny nonzero cost', () => {
    expect(usagePresentation(null)).toEqual({ label: null, title: '' });
    expect(usagePresentation({ cost: { amount: 0, currency: 'USD' } }).label).toBe('USD 0.00');
    expect(usagePresentation({ cost: { amount: 0.000001, currency: 'USD' } }).label).not.toBe('USD 0.00');
    for (const amount of [true, -1, Infinity, NaN, '0']) expect(usagePresentation({ cost: { amount, currency: 'USD' } }).label).toBeNull();
});
test('turn tokens are tooltip data, never a context percentage', () => {
    const result = usagePresentation({ turnUsage: { inputTokens: 0, outputTokens: 35, totalTokens: 3014, thoughtTokens: true } });
    expect(result.label).toBe('Turn usage');
    expect(result.title).toContain('Input: 0');
    expect(result.title).toContain('Output: 35');
    expect(result.title).not.toContain('Reasoning');
});
