import { test, expect } from 'bun:test';
import { quickActionItems, shouldOpenQuickActions } from '../../src/vibes/static/js/components/quick-actions.js';

test('quick actions use session metadata, exclude archived, dedupe and filter normalized titles/IDs/descriptions', () => {
  const options = {
    sessions: [{ id: 'default', name: 'Default' }, { id: 'no-name' }, { id: 'archived', name: 'Old', archived: 1 }, { id: 'default', name: 'Duplicate' }],
    workspace: [{ id: 'terminal', title: 'Open terminal', subtitle: 'Shell pane', run: () => {} }, { id: 'vnc', title: 'VNC' }],
    commands: [{ name: '/model', description: 'Select provider' }, { name: 'MODEL' }, { name: '/' }, null],
  };
  expect(quickActionItems(options).map(item => item.key)).toEqual(['session:default', 'session:no-name', 'workspace:terminal', 'slash:/model']);
  for (const query of ['@default', ' DEFAULT ']) expect(quickActionItems({ ...options, query }).map(i => i.key)).toEqual(['session:default']);
  expect(quickActionItems({ ...options, query: 'no-name' })[0].title).toBe('@no-name');
  expect(quickActionItems({ ...options, query: '/MODEL' })[0].commandName).toBe('/model');
  expect(quickActionItems({ ...options, query: 'shell   pane' })[0].key).toBe('workspace:terminal');
  expect(quickActionItems({ ...options, query: 'provider' })[0].key).toBe('slash:/model');
});

test('timeline typing gate excludes shortcuts, controls, composition, repeats, whitespace and consumed events', () => {
  const base = { key: 'a', target: { tagName: 'BODY' } };
  expect(shouldOpenQuickActions(base)).toBe(true);
  expect(shouldOpenQuickActions({ ...base, key: '/' })).toBe(true);
  expect(shouldOpenQuickActions({ ...base, shiftKey: true, key: 'A' })).toBe(true);
  for (const flag of ['defaultPrevented', 'isComposing', 'repeat', 'ctrlKey', 'metaKey', 'altKey']) expect(shouldOpenQuickActions({ ...base, [flag]: true })).toBe(false);
  for (const key of [' ', '\n', 'Enter', 'Dead', 'Escape']) expect(shouldOpenQuickActions({ ...base, key })).toBe(false);
  expect(shouldOpenQuickActions({ ...base, target: { isContentEditable: true } })).toBe(false);
  expect(shouldOpenQuickActions({ ...base, target: { tagName: 'INPUT', closest: () => ({}) } })).toBe(false);
});
