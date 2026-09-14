import { test, expect } from '@playwright/test';

test('active turn shows Piclaw cancel control and dispatches scoped abort', async ({ page }) => {
    let payload;
    await page.route('**/agent/default/abort', async route => {
        payload = route.request().postDataJSON();
        await route.fulfill({ json: { command: { name: 'abort', status: 'ok' } } });
    });
    await page.addInitScript(() => {
        window.EventSource = class extends EventTarget {
            constructor() { super(); window.testEventSource = this; }
            close() {}
        };
    });
    await page.goto('/');
    await expect(page.getByTestId('stop-button')).toHaveCount(0);
    await page.evaluate(() => window.testEventSource.dispatchEvent(new MessageEvent('agent_status', {
        data: JSON.stringify({ session_id: 'default', turn_id: 'turn-1', type: 'thinking', title: 'Thinking' }),
    })));
    const stop = page.getByTestId('stop-button');
    await expect(stop).toBeVisible();
    await expect(stop).toHaveClass(/abort-mode/);
    await expect(stop.locator('.compose-submit-spinner-stop')).toBeVisible();
    await stop.dispatchEvent('click');
    await expect.poll(() => payload).toEqual({ session_id: 'default', turn_id: 'turn-1' });
});

async function mockStream(page) {
    await page.addInitScript(() => {
        class Stream {
            constructor() { this.listeners = new Map(); this.readyState = 1; window.testStream = this; }
            addEventListener(type, fn) { this.listeners.set(type, fn); }
            close() {}
        }
        window.EventSource = Stream;
        window.emitTurn = (type, data) => window.testStream.listeners.get(type)?.({ data: JSON.stringify(data) });
    });
}
const active = { busy: true, active_turns: [{ turn_id: 'restored-turn', thread_id: 1, agent_id: 'default', last_status: { type: 'thinking', title: 'Thinking…' } }], pending_steers: [], queued_followups: [] };

test('restored turn keeps cancel across connected handshake and transient disconnection', async ({ page }) => {
    await mockStream(page);
    await page.route('**/agents/status?*', route => route.fulfill({ json: active }));
    await page.goto('/');
    const stop = page.getByTestId('stop-button');
    await expect(stop).toBeVisible();
    await page.evaluate(() => { window.testStream.onopen?.(); window.emitTurn('connected', {}); });
    await expect(stop).toBeVisible();
    // Handshake may arrive after the status inspection, not just before it.
    await page.evaluate(() => window.emitTurn('connected', {}));
    await expect(stop).toBeVisible();
    await page.evaluate(() => window.testStream.onerror?.());
    await expect(stop).toBeVisible();
});

test('delta-only active turn shows cancel even without status text; terminal status removes it', async ({ page }) => {
    await mockStream(page);
    await page.goto('/');
    await expect(page.locator('.compose-box textarea')).toBeVisible();
    await page.evaluate(() => window.emitTurn('agent_draft', { session_id: 'default', turn_id: 'delta-turn', text: 'In progress' }));
    await expect(page.getByTestId('stop-button')).toBeVisible();
    await page.evaluate(() => window.emitTurn('agent_status', { session_id: 'default', turn_id: 'delta-turn', type: 'cancelled' }));
    await expect(page.getByTestId('stop-button')).toHaveCount(0);
});

test('cancel is clickable during reconnect and search; pending/errors retain draft and media', async ({ page }) => {
    await mockStream(page);
    await page.route('**/agents/status?*', route => route.fulfill({ json: active }));
    let release;
    let requests = 0;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/agent/default/abort', async route => {
        requests++; await gate;
        await route.fulfill({ status: 409, json: { error: 'Turn is no longer active' } });
    });
    await page.goto('/');
    const compose = page.locator('.compose-box textarea');
    await compose.fill('preserve my draft');
    await page.locator('.compose-box input[type="file"]').setInputFiles({ name: 'keep.txt', mimeType: 'text/plain', buffer: Buffer.from('keep') });
    await expect(page.getByTestId('stop-button')).toBeVisible();
    // Real pointer click, not dispatchEvent: reconnect notice must not steal it.
    await page.getByTestId('stop-button').click();
    await expect(page.getByTestId('stop-button')).toBeDisabled();
    expect(requests).toBe(1);
    release();
    await expect(page.getByText('Turn is no longer active', { exact: true })).toBeVisible();
    await expect(compose).toHaveValue('preserve my draft');
    await expect(page.locator('.compose-box').getByText('keep.txt', { exact: true })).toBeVisible();
    await page.getByTitle('Search', { exact: true }).click();
    await expect(page.getByTestId('stop-button')).toBeVisible();
    await page.getByTitle('Close search', { exact: true }).click();
    await expect(compose).toHaveValue('preserve my draft');
});

test('late restored status cannot resurrect a completed turn; other-session events stay isolated', async ({ page }) => {
    await mockStream(page);
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/agents/status?*', async route => { await gate; await route.fulfill({ json: active }); });
    await page.goto('/');
    await expect(page.locator('.compose-box textarea')).toBeVisible();
    await page.evaluate(() => {
        window.emitTurn('agent_status', { session_id: 'default', turn_id: 'restored-turn', type: 'thinking' });
    });
    await expect(page.getByTestId('stop-button')).toBeVisible();
    await page.evaluate(() => window.emitTurn('agent_status', { session_id: 'default', turn_id: 'restored-turn', type: 'done' }));
    release();
    await expect(page.getByTestId('stop-button')).toHaveCount(0);
    await page.evaluate(() => window.emitTurn('agent_draft', { session_id: 'other', turn_id: 'other-turn', text: 'private' }));
    await expect(page.getByTestId('stop-button')).toHaveCount(0);
});

test('non-default turn cancel is scoped; switching to idle default removes stop', async ({ page }) => {
    const created = await page.request.post('/sessions', { data: { name: 'Cancel private' } });
    const session = (await created.json()).session;
    await mockStream(page);
    await page.route('**/agents/status?*', route => route.fulfill({ json: new URL(route.request().url()).searchParams.get('session_id') === session.id ? active : { busy: false, active_turns: [] } }));
    let sent;
    await page.route('**/agent/default/abort', async route => { sent = route.request().postDataJSON(); await route.fulfill({ status: 202, json: { status: 'cancelling' } }); });
    await page.goto('/');
    await page.getByTestId('session-switcher').click();
    await page.locator(`#session-option-${session.id}`).click();
    await expect(page.getByTestId('stop-button')).toBeVisible();
    await page.getByTestId('stop-button').click();
    await expect.poll(() => sent).toEqual({ session_id: session.id, turn_id: 'restored-turn' });
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-default').click();
    await expect(page.getByTestId('stop-button')).toHaveCount(0);
    await page.request.delete(`/sessions/${session.id}`);
});
