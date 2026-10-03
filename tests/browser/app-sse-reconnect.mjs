import { chromium, webkit } from '@playwright/test';

// Full built application with real EventSource; synthetic backend, not provider acceptance.
const root = process.cwd() + '/src/vibes/static';
const encoder = new TextEncoder();
let connections = 0;
let statusReads = 0;
const calls = [
    { tool_call_id: 'a', title: 'Retained completed', output: '<literal>', started_at: 1, ended_at: 2, status: 'completed' },
    { tool_call_id: 'b', title: 'Retained running', output: 'in progress', started_at: Date.now() / 1000, status: 'running' },
];
const snapshot = { type: 'writing', tool_calls: calls, tool_calls_truncated: true };
let disconnectFirst;
let disconnected = false;
const server = Bun.serve({ port: 0, idleTimeout: 0, async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === '/') return new Response('<div id="app"></div><script type="module" src="/static/dist/app.js"></script>', { headers: { 'Content-Type': 'text/html' } });
    if (url.pathname === '/agents/status') {
        if (url.searchParams.get('session_id') !== 'selected') return new Response('wrong chat', { status: 400 });
        statusReads++;
        return Response.json({ busy: true, active_turns: [{ turn_id: 'turn', thread_id: 1, agent_id: 'pi', last_status: snapshot }] });
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
                // Next connection stays open until client cleanup.
            },
            cancel() { clearTimeout(timer); },
        }), { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' } });
    }
    if (url.pathname === "/sessions") return Response.json({ sessions: [{ id: "selected", name: "Selected", archived: 0 }] });
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
    await page.goto(`http://127.0.0.1:${server.port}/?session_id=selected`);
    await page.waitForFunction(() => document.querySelectorAll(".thinking-panel").length === 2);
    await page.waitForFunction(() => document.querySelectorAll('.thinking-panel-body')[1]?.textContent === 'in progress');
    if (!disconnectFirst) throw Error('Initial SSE connection missing');
    disconnectFirst();
    await page.waitForFunction(() => document.querySelectorAll('.thinking-panel-body')[1]?.textContent === 'recovered after disconnect');
    if (!disconnected) throw Error('Disconnect was not triggered');
    if (connections < 2 || statusReads < 2) throw Error('No real transport reconnection/status refresh');
    if (await page.locator('.thinking-panel').count() !== 2) throw Error('Lost retained collection');
    await page.locator('.thinking-panel-header').first().click();
    if (!(await page.locator('.thinking-panel-body').first().innerText()).includes('<literal>')) throw Error('Lost literal completed output');
    await page.waitForFunction(() => document.querySelector('.thinking-panel-header').getAttribute('aria-expanded') === 'true');
    if (await page.locator('.thinking-panel-header').nth(1).getAttribute('aria-expanded') !== 'false') throw Error('Coupled disclosures');
    await page.locator('.thinking-panel-header').nth(1).click();
    if (!(await page.locator('.thinking-panel-body').nth(1).innerText()).includes('recovered after disconnect')) throw Error('Lost recovered running output');
    if (!(await page.locator('#app').innerText()).includes('Earlier tool calls omitted')) throw Error('Lost omission notice');
    if (errors.length) throw Error(errors.join('\n'));
    console.log(`${engine}: full app EventSource reconnect with synthetic backend passed`);
} finally {
    await browser.close();
    server.stop(true);
}
