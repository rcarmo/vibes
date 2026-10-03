import { chromium, webkit } from '@playwright/test';

// Full built application with real EventSource; synthetic backend, not provider acceptance.
const root = process.cwd() + '/src/vibes/static';
const encoder = new TextEncoder();
let queueReads = 0;
let releaseOldQueue;
let connections = 0;
let statusReads = 0;
const calls = [
    { tool_call_id: 'a', title: 'Retained completed', output: '<literal>', started_at: 1, ended_at: 2, status: 'completed' },
    { tool_call_id: 'b', title: 'Retained running', output: 'in progress', started_at: Date.now() / 1000, status: 'running' },
];
const snapshot = { type: 'writing', tool_calls: calls, tool_calls_truncated: true };
let disconnectFirst;
let disconnected = false;
let liveStream;
let completed = true;
const server = Bun.serve({ port: 0, idleTimeout: 0, async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === '/') return new Response('<div id="app"></div><script type="module" src="/static/dist/app.js"></script>', { headers: { 'Content-Type': 'text/html' } });
    if (url.pathname === '/agents/status') {
        if (!['selected', 'other'].includes(url.searchParams.get('session_id'))) return new Response('wrong chat', { status: 400 });
        statusReads++;
        return Response.json({ busy: !completed, active_turns: completed ? [] : [{ turn_id: 'turn', thread_id: 1, agent_id: 'pi', last_status: snapshot }] });
    }
    if (url.pathname === '/sse/stream') {
        const number = ++connections;
        let timer;
        return new Response(new ReadableStream({
            start(controller) {
                controller.enqueue(encoder.encode('event: connected\ndata: {}\n\n'));
                if (number === 1) disconnectFirst = () => {
                    calls[1].output = 'recovered after disconnect';
                    disconnected = true;
                    controller.close();
                };
                if (number > 1) liveStream = controller;
                liveStream = controller;
                // Next connection stays open until client cleanup.
            },
            cancel() { clearTimeout(timer); },
        }), { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' } });
    }
    if (url.pathname === "/sessions") return Response.json({ sessions: [{ id: "selected", name: "Selected", archived: 0 }, { id: "other", name: "Other", archived: 0 }] });
    if (url.pathname === "/agents") return Response.json({ agents: [{ id: "default", name: "Agent" }], user: {} });
    if (url.pathname === "/timeline") return Response.json({ posts: [], has_more: false });
    if (!url.pathname.startsWith("/static/")) return Response.json({ items: [], commands: [], hashtags: [], files: [] });
    return new Response(Bun.file(root + url.pathname.slice(7)));
} });
const engine = process.argv[2] || 'chromium';
if (!['chromium', 'webkit'].includes(engine)) throw Error('Expected chromium or webkit');
const browser = await ({ chromium, webkit })[engine].launch({ headless: true });
try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/agent/queue?**', async route => {
        if (new URL(route.request().url()).searchParams.get('session_id') === 'other') {
            await route.fulfill({ json: { items: [], uncertain: [{ row_id: -99, content: 'other chat uncertainty' }] } });
            return;
        }
        const read = ++queueReads;
        if (read === 1) await new Promise(resolve => { releaseOldQueue = resolve; });
        await route.fulfill({ json: { items: [], uncertain: [{ row_id: -read, content: read === 1 ? 'stale uncertain' : 'current uncertain' }] } });
    });
    await page.goto(`http://127.0.0.1:${server.port}/?session_id=selected`);
    await page.waitForFunction(() => window.EventSource);
    while (!liveStream || !releaseOldQueue) await Bun.sleep(10);
    liveStream.enqueue(encoder.encode('event: agent_followup_queued\ndata: {"session_id":"selected"}\n\n'));
    await page.getByText('current uncertain', { exact: true }).waitFor({timeout: 20000}).catch(async error => { console.log('DOM', await page.locator('body').innerText()); throw error; });
    const oldResponse = page.waitForResponse(response => response.url().includes('/agent/queue'));
    releaseOldQueue();
    await oldResponse;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    if (await page.getByText('stale uncertain', { exact: true }).count()) throw new Error('stale queue response replaced current uncertainty');
    await page.getByText('current uncertain', { exact: true }).waitFor({timeout: 12000}).catch(async error => { console.log('DOM', await page.locator('body').innerText()); throw error; });
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-other').click();
    await page.getByText('other chat uncertainty', { exact: true }).waitFor();
    if (await page.getByText('current uncertain', { exact: true }).count()) throw new Error('old chat uncertainty leaked after switch');
    if (errors.length) throw Error(errors.join('\n'));
    console.log(`${engine}: full app stale uncertain queue response rejected (synthetic backend)`);
} finally {
    await browser.close();
    server.stop(true);
}
