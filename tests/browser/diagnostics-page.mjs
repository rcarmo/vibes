import { chromium, webkit } from '@playwright/test';
const root = process.cwd() + '/src/vibes/static';
let reads = 0;
let wrongSession = false;
const server = Bun.serve({ port: 0, async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === '/diagnostics/backend') {
        reads++;
        return Response.json({ session_id: wrongSession ? 'foreign' : url.searchParams.get('session_id'), execution_verified: false, tools: [{ name: '<img src=x onerror=alert(1)>', state: 'configured' }] });
    }
    return new Response(Bun.file(root + (url.pathname === '/' ? '/diagnostics.html' : url.pathname.replace('/static', ''))));
} });
const engine = process.argv[2] || 'chromium';
const browser = await ({ chromium, webkit })[engine].launch();
try {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${server.port}/?session_id=selected`);
    if (reads !== 0) throw Error('Automatic diagnostic RPC');
    await page.getByRole('button', { name: 'Refresh diagnostics' }).click();
    await page.waitForFunction(() => document.querySelector('#result').textContent.includes('selected'));
    if (await page.locator('#result img').count()) throw Error('Metadata interpreted as HTML');
    if (!(await page.locator('#result').innerText()).includes('<img')) throw Error('Lost literal label');
    await page.locator('#session').fill('other');
    if (await page.locator('#result').innerText()) throw Error('Stale snapshot after chat change');
    if (reads !== 1) throw Error('Chat change triggered inspection');
    wrongSession = true;
    await page.getByRole('button', { name: 'Refresh diagnostics' }).click();
    await page.waitForFunction(() => document.querySelector('#state').textContent.startsWith('Inspection unavailable.'));
    if (await page.locator('#result').innerText()) throw Error('Wrong-chat snapshot rendered');
    console.log(`${engine}: on-demand diagnostics, safe text and response ownership passed`);
} finally { await browser.close(); server.stop(true); }
