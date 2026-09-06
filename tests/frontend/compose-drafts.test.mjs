import { test, expect } from 'bun:test';
import { ComposeDrafts } from '../../src/vibes/static/js/components/compose-drafts.js';

test('session draft metadata persists but file bytes do not', () => {
    const values = new Map();
    const storage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
    const drafts = new ComposeDrafts(storage);
    const file = new File(['private bytes'], 'draft.txt');
    drafts.save('a', { text: 'unsent', files: [file], fileRefs: ['a.txt'], folderRefs: ['src'], messageRefs: ['42'] });
    drafts.save('b', { text: 'other' });
    expect(drafts.load('a').text).toBe('unsent');
    expect(drafts.load('b').text).toBe('other');
    expect(drafts.load('a').files[0]).toBe(file);
    expect([...values.values()].join('')).not.toContain('private bytes');
    expect(new ComposeDrafts(storage).load('a').files).toEqual([]);
    expect(new ComposeDrafts(storage).load('a').folderRefs).toEqual(['src']);
    drafts.clear('a');
    expect(drafts.load('a').text).toBe('');
    expect(drafts.load('b').text).toBe('other');
});

test('malformed storage and quota failures are safe', () => {
    const drafts = new ComposeDrafts({ getItem: () => '{', setItem: () => { throw Error('quota'); }, removeItem: () => { throw Error('denied'); } });
    expect(drafts.load('default').text).toBe('');
    expect(() => drafts.save('default', { text: 'draft' })).not.toThrow();
    expect(() => drafts.clear('default')).not.toThrow();
});
