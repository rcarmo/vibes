import { test, expect } from 'bun:test';
import { SessionNavigation } from '../../src/vibes/static/js/components/session-navigation.js';

function deferred() { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; }

test('latest switch commits matching timeline and draft together', async () => {
    const a = deferred(), b = deferred(), commits = [];
    const nav = new SessionNavigation({ loadTimeline: id => id === 'a' ? a.promise : b.promise, drafts: { load: id => ({ text: id }) }, commit: value => commits.push(value) });
    const first = nav.select('a'), second = nav.select('b');
    b.resolve({ posts: [{ id: 2 }], has_more: true });
    expect(await second).toBe(true);
    a.resolve({ posts: [{ id: 1 }] });
    expect(await first).toBe(false);
    expect(commits).toEqual([{ sessionId: 'b', posts: [{ id: 2 }], hasMore: true, draft: { text: 'b' } }]);
});

test('failed current switch preserves UI and disposed requests cannot commit', async () => {
    const pending = deferred(), commits = [];
    const nav = new SessionNavigation({ loadTimeline: () => pending.promise, drafts: { load: () => ({}) }, commit: value => commits.push(value) });
    const result = nav.select('a');
    nav.dispose();
    pending.resolve({ posts: [] });
    expect(await result).toBe(false);
    expect(commits).toEqual([]);
    const fail = new SessionNavigation({ loadTimeline: async () => { throw Error('offline'); }, drafts: {}, commit: value => commits.push(value) });
    await expect(fail.select('b')).rejects.toThrow('offline');
    expect(commits).toEqual([]);
});
