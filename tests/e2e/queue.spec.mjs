import { test, expect } from '@playwright/test';

test('queue move buttons submit direction and reflect server order', async ({ page }) => {
    let items = [{ row_id: -1, content: 'first queued', agent_id: 'default', thread_id: 1 }, { row_id: -2, content: 'second queued', agent_id: 'default', thread_id: 1 }];
    let payload;
    await page.route('**/agent/queue?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items, pending_steers: [] }) }));
    await page.route('**/agent/queue-reorder', async route => {
        payload = route.request().postDataJSON();
        items = [items[1], items[0]];
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items }) });
    });
    await page.goto('/');
    const rows = page.locator('.compose-queue-item');
    await expect(rows).toHaveCount(2);
    await expect(rows.first().getByRole('button', { name: 'Move up in queue' })).toBeDisabled();
    await rows.nth(1).getByRole('button', { name: 'Move up in queue' }).click();
    await expect(rows.first()).toContainText('second queued');
    expect(payload).toEqual({ row_id: -2, direction: 'up' });
});

test('queued reference blocks render as pills without hiding invalid lines', async ({ page }) => {
    const content = 'Review this\n\nFiles:\n- src/main.py\n\nMessages:\n- 42\n- invalid-ref\n\nAttachments:\n- attachment:7 (notes.txt)';
    await page.route('**/agent/queue?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [{ row_id: -1, content, agent_id: 'default', thread_id: 1 }] }) }));
    await page.goto('/');
    const row = page.locator('.compose-queue-item');
    await expect(row.locator('.compose-file-pill')).toHaveCount(3);
    await expect(row.locator('.compose-file-pill', { hasText: 'main.py' })).toBeVisible();
    await expect(row.locator('.compose-file-pill', { hasText: 'msg:42' })).toBeVisible();
    await expect(row.locator('.compose-file-pill', { hasText: 'notes.txt' })).toBeVisible();
    await expect(row.locator('.compose-queue-text')).toContainText('invalid-ref');
});

test('older queue refresh cannot overwrite a newer reorder notification', async ({ page }) => {
    await page.addInitScript(() => {
        window.EventSource = class extends EventTarget {
            constructor() { super(); window.testEventSource = this; }
            close() {}
        };
    });
    const snapshot = content => ({ items: [{ row_id: -1, content, agent_id: 'default', thread_id: 1 }] });
    await page.route('**/agent/queue?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(snapshot('Initial queue')) }));
    await page.goto('/');
    const row = page.locator('.compose-queue-item');
    await expect(row).toContainText('Initial queue');
    let release;
    const held = new Promise(resolve => { release = resolve; });
    let requests = 0;
    await page.route('**/agent/queue?*', async route => {
        const index = ++requests;
        if (index === 1) await held;
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(snapshot(index === 1 ? 'Old queue' : 'New queue')) });
    });
    const emit = () => page.evaluate(() => window.testEventSource.dispatchEvent(new MessageEvent('agent_queue_reordered', { data: '{}' })));
    await emit();
    await expect.poll(() => requests).toBe(1);
    await emit();
    await expect(row).toContainText('New queue');
    const response = page.waitForResponse(res => res.url().includes('/agent/queue?'));
    release();
    await response;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(row).toContainText('New queue');
});

test('queue response from a previous visit cannot replace the revisited session queue', async ({ page }) => {
    await page.addInitScript(() => {
        window.EventSource = class extends EventTarget {
            constructor() { super(); window.testEventSource = this; }
            close() {}
        };
    });
    let holdNext = false;
    let waiting = false;
    let release;
    const held = new Promise(resolve => { release = resolve; });
    let revisiting = false;
    await page.route('**/agent/queue?*', async route => {
        const session = new URL(route.request().url()).searchParams.get('session_id');
        let content = session === 'default' ? (revisiting ? 'Fresh A queue' : 'Initial A queue') : 'B queue';
        if (holdNext && session === 'default') {
            holdNext = false;
            waiting = true;
            content = 'Stale A queue';
            await held;
        }
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({
            items: [{ row_id: -1, content, agent_id: 'default', thread_id: 1 }],
        }) });
    });
    await page.goto('/');
    const row = page.locator('.compose-queue-item');
    await expect(row).toContainText('Initial A queue');
    const created = await page.request.post('/sessions', { data: { name: 'Queue B' } });
    const id = (await created.json()).session.id;
    holdNext = true;
    await page.evaluate(() => window.testEventSource.dispatchEvent(new MessageEvent('agent_queue_reordered', { data: '{}' })));
    await expect.poll(() => waiting).toBe(true);
    const trigger = page.getByTestId('session-switcher');
    await trigger.click();
    await page.locator(`#session-option-${id}`).click();
    await expect(row).toContainText('B queue');
    revisiting = true;
    await trigger.click();
    await page.locator('#session-option-default').click();
    await expect(row).toContainText('Fresh A queue');
    const response = page.waitForResponse(res => res.url().includes('/agent/queue?'));
    release();
    await response;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(row).toContainText('Fresh A queue');
});
