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
    const stack = page.locator('.compose-queue-stack');
    const rows = page.locator('.compose-queue-stack-item');
    await expect(rows).toHaveCount(2);
    await expect(stack.locator('xpath=following-sibling::*[1]')).toHaveClass(/compose-input-wrapper/);
    await expect(page.locator('.compose-box > .compose-queue-stack')).toHaveCount(1);
    await expect(page.locator('.compose-input-wrapper .compose-queue-stack')).toHaveCount(0);
    await expect(rows.first().getByRole('button', { name: 'Move up in queue' })).toBeDisabled();
    await rows.nth(1).getByRole('button', { name: 'Move up in queue' }).click();
    await expect(rows.first()).toContainText('second queued');
    expect(payload).toEqual({ row_id: -2, direction: 'up' });
});

test('idle queued items disable steering and send no request', async ({ page }) => {
    let requests = 0;
    await page.route('**/agent/queue?*', route => route.fulfill({ json: { items: [{ row_id: -1, content: 'Idle queued', agent_id: 'default', thread_id: 1 }], pending_steers: [] } }));
    await page.route('**/agent/queue-steer', route => { requests++; return route.fulfill({ json: {} }); });
    await page.goto('/');
    const steer = page.getByRole('button', { name: /Promote queued item to steering/ });
    await expect(steer).toBeDisabled();
    await expect(steer).toHaveAttribute('title', 'Steering requires a matching active turn');
    await steer.press('Enter');
    expect(requests).toBe(0);
});

test('active queued item steering submits its durable ID once', async ({ page }) => {
    let requests = [];
    await page.addInitScript(() => { window.EventSource = class extends EventTarget { constructor(){ super(); window.testEventSource=this; } close(){} }; });
    await page.route('**/agent/queue?*', route => route.fulfill({ json: { items: [{ row_id: -7, content: 'Active queued', agent_id: 'default', thread_id: 1 }], pending_steers: [] } }));
    await page.route('**/agent/queue-steer', async route => { requests.push(route.request().postDataJSON()); await new Promise(resolve=>setTimeout(resolve,30)); await route.fulfill({ json: { status: 'ok' } }); });
    await page.goto('/');
    await page.evaluate(() => window.testEventSource.dispatchEvent(new MessageEvent('agent_status', { data: JSON.stringify({ session_id: 'default', turn_id: 'turn-1', type: 'thinking', title: 'Thinking' }) })));
    const steer = page.getByRole('button', { name: /Promote queued item to steering/ });
    await expect(steer).toBeEnabled();
    await steer.click(); await steer.click({ force: true });
    await expect.poll(() => requests.length).toBe(1);
    expect(requests[0]).toEqual({ row_id: -7 });
});

test('return to editor preserves latest draft before deleting and ignores duplicate activation', async ({ page }) => {
    let releases, deletes = 0;
    await page.route('**/agent/queue?*', route => route.fulfill({ json: { items: [{ row_id: -4, content: 'Recovered queued text', agent_id: 'default', thread_id: 1 }], pending_steers: [] } }));
    await page.route('**/agent/queue-remove', async route => { deletes++; await new Promise(resolve => { releases = resolve; }); await route.fulfill({ json: { removed: true } }); });
    await page.goto('/');
    const editor = page.locator('.compose-box textarea'); await editor.fill('Draft before request');
    page.once('dialog', dialog => dialog.accept());
    const button = page.getByRole('button', { name: 'Return queued message to editor' });
    await button.click(); await expect.poll(() => !!releases).toBe(true);
    await button.click({ force: true }); expect(deletes).toBe(1);
    await editor.fill('Newer draft while deleting'); releases();
    await expect(editor).toHaveValue('Newer draft while deleting\n\nRecovered queued text');
    expect(JSON.parse(await page.evaluate(() => localStorage.getItem('vibes_compose_draft:default'))).text).toContain('Recovered queued text');
});

test('return to editor writes only the origin draft when session switches in flight', async ({ page }) => {
    const created = await page.request.post('/sessions', { data: { name: 'Queue destination' } });
    const other = (await created.json()).session.id;
    let release;
    await page.route('**/agent/queue?*', route => {
        const session = new URL(route.request().url()).searchParams.get('session_id');
        return route.fulfill({ json: { items: session === 'default' ? [{ row_id: -8, content: 'Origin queued', agent_id: 'default', thread_id: 1 }] : [], pending_steers: [] } });
    });
    await page.route('**/agent/queue-remove', async route => { await new Promise(resolve => { release = resolve; }); await route.fulfill({ json: { removed: true } }); });
    await page.goto('/'); const editor = page.locator('.compose-box textarea'); await editor.fill('Origin latest');
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Return queued message to editor' }).click(); await expect.poll(() => !!release).toBe(true);
    await page.getByTestId('session-switcher').click(); await page.locator(`#session-option-${other}`).click();
    await expect(page.getByTestId('session-switcher')).toContainText('Queue destination');
    await editor.fill('Other draft');
    release(); await expect(editor).toHaveValue('Other draft');
    await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('vibes_compose_draft:default') || '{}').text)).toBe('Origin latest\n\nOrigin queued');
    await expect.poll(() => page.evaluate(id => JSON.parse(localStorage.getItem(`vibes_compose_draft:${encodeURIComponent(id)}`) || '{}').text, other)).toBe('Other draft');
});

test('return to editor storage failure prevents queue deletion', async ({ page }) => {
    let deletes = 0;
    await page.addInitScript(() => { const original=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key.startsWith('vibes_queue_return:'))throw new Error('fixture quota');return original.call(this,key,value);}; });
    await page.route('**/agent/queue?*', route => route.fulfill({ json: { items: [{ row_id: -5, content: 'Preserve me', agent_id: 'default', thread_id: 1 }], pending_steers: [] } }));
    await page.route('**/agent/queue-remove', route => { deletes++; return route.fulfill({ json: { removed: true } }); });
    await page.goto('/');let message='';page.once('dialog',async dialog=>{message=dialog.message();await dialog.accept();});
    await page.getByRole('button', { name: 'Return queued message to editor' }).click();
    await expect.poll(()=>message).toContain('fixture quota');expect(deletes).toBe(0);
    await expect(page.locator('.compose-queue-stack-item')).toContainText('Preserve me');
});

test('queued steering renders the classic queued turn dot', async ({ page }) => {
    await page.addInitScript(() => {
        window.EventSource = class extends EventTarget {
            constructor() { super(); window.testEventSource = this; }
            close() {}
        };
    });
    await page.route('**/agent/queue?*', route => route.fulfill({ json: { items: [], pending_steers: [] } }));
    await page.goto('/');
    await page.evaluate(() => {
        window.testEventSource.dispatchEvent(new MessageEvent('agent_status', { data: JSON.stringify({ session_id: 'default', turn_id: 'turn-1', type: 'thinking', title: 'Thinking' }) }));
        window.testEventSource.dispatchEvent(new MessageEvent('agent_steer_queued', { data: JSON.stringify({ session_id: 'default', turn_id: 'turn-1', row_id: -7 }) }));
        window.testEventSource.dispatchEvent(new MessageEvent('agent_thought', { data: JSON.stringify({ session_id: 'default', turn_id: 'turn-1', text: 'Thinking preview', mode: 'replace', total_lines: 1 }) }));
    });
    await expect(page.locator('.agent-status-panel .agent-thinking .turn-dot-queued')).toBeVisible();
    await expect(page.locator('.agent-status-panel .agent-status-spinner')).toBeVisible();
});

test('queued reference blocks render as pills without hiding invalid lines', async ({ page }) => {
    const content = 'Review this\n\nFiles:\n- src/main.py\n\nMessages:\n- 42\n- invalid-ref\n\nAttachments:\n- attachment:7 (notes.txt)';
    await page.route('**/agent/queue?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [{ row_id: -1, content, agent_id: 'default', thread_id: 1 }] }) }));
    await page.goto('/');
    const row = page.locator('.compose-queue-stack-item');
    await expect(row.locator('.compose-file-pill')).toHaveCount(3);
    await expect(row.locator('.compose-file-pill', { hasText: 'main.py' })).toBeVisible();
    await expect(row.locator('.compose-file-pill', { hasText: 'msg:42' })).toBeVisible();
    await expect(row.locator('.compose-file-pill', { hasText: 'notes.txt' })).toBeVisible();
    await expect(row.locator('.compose-queue-stack-text')).toContainText('invalid-ref');
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
    const row = page.locator('.compose-queue-stack-item');
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
    const row = page.locator('.compose-queue-stack-item');
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
