import { describe, expect, test } from 'bun:test';
import { DEFAULT_SLASH_COMMANDS, normalizeSlashCommands } from '../../static/js/features/compose/slash-commands.ts';

describe('slash command utilities', () => {
  test('ships base commands', () => {
    expect(DEFAULT_SLASH_COMMANDS.some((cmd) => cmd.name === '/model')).toBe(true);
    expect(DEFAULT_SLASH_COMMANDS.some((cmd) => cmd.name === '/user-github')).toBe(true);
  });

  test('normalizes array and wrapped command payloads', () => {
    expect(normalizeSlashCommands([{ name: ' /x ', description: 'test' }, { name: '' }, null]).map((cmd) => cmd.name)).toEqual(['/x']);
    expect(normalizeSlashCommands({ commands: [{ name: '/y' }] })).toEqual([{ name: '/y', description: '' }]);
  });
});
