import { chromium, webkit } from '@playwright/test';

// Real EventSource transport; synthetic server snapshots, not a provider fixture.
const root = process.cwd() + '/src/vibes/static';
const encoder = new TextEncoder();
let connections = 0;
let statusReads = 0;
const calls = [
    { tool_call_id: 'a', title: 'Retained completed', output: '<literal>', started_at: 1, ended_at: 2, status: 'completed' },
    { tool_call_id: 'b', title: 'Retained running', output: 'in progress', started_at: Date.now() / 1000, status: 'running' },
];
const snapshot = { type: 'writing', tool_calls: calls, tool_calls_truncated: true };
const server = Bun.serve({ port: 0, idleTimeout: 0, async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === '/') return new Response('<div id="root"></div>', { headers: { 'Content-Type': 'text/html' } });
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
                if (number === 1) timer = setTimeout(() => controller.close(), 200);
                // Next connection stays open until client cleanup.
            },
            cancel() { clearTimeout(timer); },
        }), { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' } });
    }
    return new Response(Bun.file(root + url.pathname));
} });
const engine = process.argv[2] || 'chromium';
if (!['chromium', 'webkit'].includes(engine)) throw Error('Expected chromium or webkit');
const browser = await ({ chromium, webkit })[engine].launch({ headless: true });
try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.port}`);
    await page.evaluate(async () => {
        const { html, render } = await import('/js/vendor/preact-htm.js');
        const { AgentStatus } = await import('/js/components/status.js');
        const { SSEClient, getAgentStatus } = await import('/js/api.js');
        window.recoveries = 0;
        window.client = new SSEClient(() => {}, async connection => {
            if (connection !== 'connected') return;
            const result = await getAgentStatus('selected');
            render(html`<${AgentStatus} status=${result.active_turns[0].last_status} renderMarkdown=${x => x} />`, document.querySelector('#root'));
            window.recoveries++;
        });
        window.client.connect();
    });
    await page.waitForFunction(() => window.recoveries >= 2);
    await page.waitForFunction(() => document.querySelectorAll('.thinking-panel').length === 2);
    if (connections < 2 || statusReads < 2) throw Error('No real transport reconnection/status refresh');
    if (await page.locator('.thinking-panel').count() !== 2) throw Error('Lost retained collection');
    await page.locator('.thinking-panel-header').first().click();
    if (!(await page.locator('.thinking-panel-body').first().innerText()).includes('<literal>')) throw Error('Lost literal completed output');
    await page.waitForFunction(() => document.querySelector('.thinking-panel-header').getAttribute('aria-expanded') === 'true');
    if (await page.locator('.thinking-panel-header').nth(1).getAttribute('aria-expanded') !== 'false') throw Error('Coupled disclosures');
    await page.locator('.thinking-panel-header').nth(1).click();
    if (!(await page.locator('.thinking-panel-body').nth(1).innerText()).includes('in progress')) throw Error('Lost running output');
    if (!(await page.locator('#root').innerText()).includes('Earlier tool calls omitted')) throw Error('Lost omission notice');
    if (errors.length) throw Error(errors.join('\n'));
    await page.evaluate(() => window.client.disconnect());
    console.log(`${engine}: real EventSource reconnect and synthetic status reconstruction passed`);
} finally {
    await browser.close();
    server.stop(true);
}
