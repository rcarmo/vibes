import { chromium, webkit, expect } from '@playwright/test';
const engine = process.argv[2] || 'chromium';
const root = process.cwd() + '/src/vibes/static';
const server = Bun.serve({ port: 0, async fetch(req) {
    const path = new URL(req.url).pathname;
    if (path !== '/') return new Response(Bun.file(root + path));
    return new Response(`<!doctype html><div id="app"></div><script type="module">
        import { html, render } from '/js/vendor/preact-htm.js';
        import { UncertainFollowups } from '/js/components/uncertain-followups.js';
        window.calls = []; window.fail = false;
        window.mount = (key = 'default', items = [{ row_id: -1, content: '<img src=x onerror=alert(1)>' }]) =>
            render(html\`<\${UncertainFollowups} key=\${key} items=\${items} onDiscard=\${async id => {
                window.calls.push(id);
                if (window.fail) throw new Error('private error');
                window.mount(key, []);
            }}/>\`, document.getElementById('app'));
        window.mount();
    </script>`, { headers: { 'Content-Type': 'text/html' } });
}});
const browser = await ({ chromium, webkit }[engine]).launch({ headless: true });
try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://localhost:${server.port}`);
    const section = page.getByRole('region', { name: 'Uncertain follow-ups' });
    await expect(section).toContainText('will not be retried automatically');
    await expect(section).toContainText('<img src=x onerror=alert(1)>');
    await expect(section.locator('img')).toHaveCount(0);
    page.once('dialog', dialog => dialog.dismiss());
    await page.getByRole('button', { name: 'Discard without retry' }).click();
    expect(await page.evaluate(() => window.calls)).toEqual([]);
    await page.evaluate(() => { window.fail = true; });
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Discard without retry' }).click();
    await expect(page.getByRole('alert')).toHaveText('Could not discard item. Refresh and review again.');
    await expect(section).not.toContainText('private error');
    await page.evaluate(() => { window.fail = false; window.mount('other'); });
    await expect(page.getByRole('alert')).toHaveCount(0);
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Discard without retry' }).click();
    await expect(section).toHaveCount(0);
    expect(await page.evaluate(() => window.calls)).toEqual([-1, -1]);
    expect(errors).toEqual([]);
    console.log(`PASS ${engine}: uncertain review escaping, confirmation, failure, remount and discard`);
} finally { await browser.close(); server.stop(true); }
