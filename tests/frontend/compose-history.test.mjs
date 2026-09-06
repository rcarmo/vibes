import { test, expect } from 'bun:test';
import { loadComposeHistory, saveComposeHistory } from '../../src/vibes/static/js/components/compose-history.js';

test('history isolates sessions and only default inherits legacy', () => {
    const values = new Map([['vibes_compose_history', '["old","old",null]']]);
    const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
    expect(loadComposeHistory(storage, 'default')).toEqual(['old']);
    expect(loadComposeHistory(storage, 'other')).toEqual([]);
    saveComposeHistory(storage, 'other', ['private']);
    expect(loadComposeHistory(storage, 'other')).toEqual(['private']);
    expect(loadComposeHistory(storage, 'default')).toEqual(['old']);
    saveComposeHistory(storage, 'default', []);
    expect(loadComposeHistory(storage, 'default')).toEqual([]);
});

test('storage errors are nonfatal', () => {
    const storage = { getItem() { throw Error('denied'); }, setItem() { throw Error('denied'); } };
    expect(loadComposeHistory(storage)).toEqual([]);
    expect(() => saveComposeHistory(storage, 'default', ['message'])).not.toThrow();
});
