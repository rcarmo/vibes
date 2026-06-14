import { describe, expect, test } from 'bun:test';
import {
  consumeEditorPopoutState,
  consumePanePopoutTransferToken,
  createEditorPopoutTransferPayload,
  EDITOR_POPOUT_STATE_TTL_MS,
  stashEditorPopoutState,
} from '../../static/js/panes/editor-popout-transfer.ts';

function createStorage() {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => { map.set(key, value); },
    removeItem: (key: string) => { map.delete(key); },
    size: () => map.size,
  };
}

describe('editor popout transfer', () => {
  test('stashes and consumes state once', () => {
    const storage = createStorage();
    const runtime = { localStorage: storage };
    const token = stashEditorPopoutState({
      path: ' notes.md ',
      content: 'hello',
      mtime: ' 2026-01-01 ',
      paneOverrideId: ' pane-1 ',
      viewState: { cursorLine: 2, cursorCol: 4, scrollTop: 10 },
    }, runtime, 1000);

    expect(token).toBeTruthy();
    expect(storage.size()).toBe(1);
    expect(consumeEditorPopoutState(token, runtime, 1000)).toMatchObject({
      path: 'notes.md',
      content: 'hello',
      mtime: '2026-01-01',
      paneOverrideId: 'pane-1',
      viewState: { cursorLine: 2, cursorCol: 4, scrollTop: 10 },
      capturedAt: 1000,
    });
    expect(consumeEditorPopoutState(token, runtime, 1000)).toBeNull();
  });

  test('rejects empty state and expired state', () => {
    const storage = createStorage();
    const runtime = { localStorage: storage };
    expect(stashEditorPopoutState({ path: 'file.md' }, runtime, 1000)).toBeNull();

    const token = stashEditorPopoutState({ path: 'file.md', content: 'x' }, runtime, 1000);
    expect(consumeEditorPopoutState(token, runtime, 1000 + EDITOR_POPOUT_STATE_TTL_MS + 1)).toBeNull();
  });

  test('creates payload and consumes URL token', () => {
    const storage = createStorage();
    const payload = createEditorPopoutTransferPayload({ path: 'file.md', content: 'x' }, { localStorage: storage }, 1000);
    const token = payload?.editor_popout;
    expect(token).toBeTruthy();
    if (!token) throw new Error('missing transfer token');

    let replacedUrl = '';
    const runtime = {
      location: { href: `https://example.test/?editor_popout=${token}&x=1` } as Location,
      history: { state: null, replaceState: (_state: unknown, _title: string, url?: string | URL | null) => { replacedUrl = String(url); } } as History,
      document: { title: 'test' } as Document,
    };
    expect(consumePanePopoutTransferToken('editor_popout', runtime)).toBe(token);
    expect(replacedUrl).toBe('https://example.test/?x=1');
  });
});
