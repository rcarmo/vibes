import { test, expect } from '@playwright/test';

test('active turn shows Piclaw cancel control and dispatches scoped abort', async ({ page }) => {
    let payload;
    await page.route('**/agent/default/message', async route => {
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
    await expect.poll(() => payload).toEqual({ content: '/abort', media_ids: [], mode: 'steer', session_id: 'default', thread_id: null });
});
