import { test, expect } from 'bun:test';
import { canonicalState, createCaseState } from './canonical-state.mjs';
import { createCases, behaviorContracts } from './cases.mjs';
test('canonical semantic state is independent per capture and keeps wire IDs out', () => {
  const a = createCaseState('working'), b = createCaseState('working');
  a.plan.markdown = 'changed'; a.sessions[0].name = 'changed'; a.metrics.cpu_series.push(99);
  expect(b.plan.markdown).toBe(canonicalState.plan.markdown);
  expect(b.sessions[0].name).toBe('Fixture session');
  expect(b.metrics.cpu_series).toEqual([10, 15, 25]);
  expect(b.metrics.process_rss_bytes).toBe(104857600);
  expect(b.queue).toHaveLength(2);
  expect(b.activity.active).toBe(true);
  expect(b.model.thinkingLevels).toEqual(['off', 'low', 'medium', 'high']);
  expect(b.context.compactCommand).toBe('/compact');
  expect(createCaseState('idle').messages).toEqual([]);
  expect(createCaseState('plan-open').ui.planOpen).toBe(true);
});
test('canonical matrix has explicit repeats and separate model tool gate', () => {
  const cases = createCases();
  expect(cases).toHaveLength(132);
  expect(new Set(cases.map(item => item.id)).size).toBe(cases.length);
  expect(cases.every(item => item.repeats === 2 && item.requires.includes('planSidebar'))).toBe(true);
  expect(behaviorContracts[0].requires).toContain('planTool');
  expect(() => createCaseState('invented')).toThrow();
  expect(() => createCases({ engines: ['invented'] })).toThrow();
});
