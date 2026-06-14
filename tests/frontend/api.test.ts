import { afterEach, describe, expect, test } from 'bun:test';
import { getMediaUrl, getThumbnailUrl, getWorkspaceDownloadUrl, getWorkspaceRawUrl, request } from '../../static/js/api.ts';

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe('api client utilities', () => {
  test('builds media and workspace URLs', () => {
    expect(getMediaUrl('abc')).toBe('/media/abc');
    expect(getThumbnailUrl('abc')).toBe('/media/abc/thumbnail');
    expect(getWorkspaceRawUrl('notes/a b.md')).toBe('/workspace/raw?path=notes%2Fa%20b.md');
    expect(getWorkspaceDownloadUrl('notes', true)).toBe('/workspace/download?path=notes&show_hidden=true');
  });

  test('request parses JSON response', async () => {
    globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
      expect(String(url)).toBe('/ok');
      expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json');
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as unknown as typeof fetch;

    await expect(request('/ok')).resolves.toEqual({ ok: true });
  });

  test('request throws backend error message', async () => {
    globalThis.fetch = (async () => new Response(JSON.stringify({ error: 'nope' }), { status: 400 })) as unknown as typeof fetch;
    await expect(request('/fail')).rejects.toThrow('nope');
  });
});
