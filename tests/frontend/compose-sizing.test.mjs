import { test, expect } from 'bun:test';
import { composeLimits, clampComposeHeight } from '../../src/vibes/static/js/components/compose-sizing.js';

test('composer sizing uses deployed desktop/mobile and viewport caps', () => {
    expect(composeLimits(1280, 844)).toEqual({ min: 70, auto: 300, max: 422 });
    expect(composeLimits(390, 844)).toEqual({ min: 50, auto: 300, max: 422 });
    expect(composeLimits(1280, 1600).max).toBe(520);
    expect(composeLimits(390, 400)).toEqual({ min: 50, auto: 160, max: 200 });
    expect(clampComposeHeight(-100, 1280, 844)).toBe(70);
    expect(clampComposeHeight(9999, 390, 844)).toBe(422);
    expect(clampComposeHeight(NaN, 390, 844)).toBe(50);
});
