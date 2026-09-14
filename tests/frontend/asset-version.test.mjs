import { test, expect } from 'bun:test';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const staticUrl = new URL('../../src/vibes/static/', import.meta.url);

test('HTML references the content version of both bundled entrypoints, including fallback import', () => {
    const version = createHash('sha256')
        .update(readFileSync(new URL('dist/app.js', staticUrl)))
        .update(readFileSync(new URL('dist/app.css', staticUrl)))
        .digest('hex').slice(0, 16);
    const index = readFileSync(new URL('index.html', staticUrl), 'utf8');
    const urls = [...index.matchAll(/\/static\/dist\/app\.(js|css)\?v=([^"'\s]+)/g)];
    expect(urls.map(match => match[1])).toEqual(['css', 'js', 'js']);
    expect(urls.map(match => match[2])).toEqual([version, version, version]);
    expect(index).not.toContain('?v=1"');
});
