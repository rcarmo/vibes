import { test, expect } from '@playwright/test';

test('app switches sessions with separate drafts and explicit send identity', async ({ page }) => {
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Other chat' } });
    const id = (await created.json()).session.id;
    const input = page.locator('.compose-input-main textarea');
    await input.fill('default draft');
    await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('vibes_compose_draft:default') || '{}').text)).toBe('default draft');
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await expect(input).toHaveValue('');
    await input.fill('other draft');
    await expect.poll(() => page.evaluate(key => JSON.parse(localStorage.getItem('vibes_compose_draft:' + key) || '{}').text, id)).toBe('other draft');
    await page.getByTestId('session-switcher').click();
    await page.getByRole('option').filter({ hasText: 'Default' }).click();
    await expect(input).toHaveValue('default draft');
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await expect(input).toHaveValue('other draft');
    let sent;
    await page.route('**/agent/default/message', async route => { sent = route.request().postDataJSON(); await route.fulfill({ contentType: 'application/json', body: '{"status":"queued"}' }); });
    await input.press('Enter');
    await expect.poll(() => sent?.session_id).toBe(id);
});

test('late search response cannot overwrite another session timeline', async ({ page }) => {
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    let searchStarted = false;
    await page.route('**/search?*', async route => {
        searchStarted = true;
        await gate;
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ results: [{ id: 987654, timestamp: new Date().toISOString(), data: { type: 'user_message', content: 'STALE SEARCH RESULT', session_id: 'default' } }] }) });
    });
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Search isolation' } });
    const id = (await created.json()).session.id;
    await page.getByTitle('Search', { exact: true }).click();
    await page.getByPlaceholder('Search (Enter to run)...').fill('old query');
    await page.getByPlaceholder('Search (Enter to run)...').press('Enter');
    await expect.poll(() => searchStarted).toBe(true);
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await expect(page.getByTestId('session-switcher')).toContainText('Search isolation');
    const response = page.waitForResponse(r => r.url().includes('/search?'));
    release();
    await response;
    await expect(page.getByText('STALE SEARCH RESULT', { exact: true })).toHaveCount(0);
});

test('picker archives and restores a session without deleting history', async ({ page }) => {
    await page.goto('/');
    const result = await page.request.post('/sessions', { data: { name: 'Archive test' } });
    const id = (await result.json()).session.id;
    await page.getByTestId('session-switcher').click();
    const row = page.locator('#session-option-' + id).locator('..');
    await row.getByRole('button', { name: 'Archive Archive test', exact: true }).click();
    await expect(page.getByRole('group', { name: 'Archived', exact: true }).locator('#session-option-' + id)).toBeVisible();
    await row.getByRole('button', { name: 'Restore Archive test', exact: true }).click();
    await expect(row.getByRole('button', { name: 'Archive Archive test', exact: true })).toBeVisible();
});

test('open picker refreshes registry changes from another client', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('session-switcher').click();
    const result = await page.request.post('/sessions', { data: { name: 'External create' } });
    const id = (await result.json()).session.id;
    await expect(page.locator('#session-option-' + id)).toBeVisible({ timeout: 10000 });
    await page.request.patch('/sessions/' + id, { data: { name: 'External rename' } });
    await expect(page.locator('#session-option-' + id)).toContainText('External rename', { timeout: 10000 });
});

test('selected chat loads only its scoped queue endpoint', async ({ page }) => {
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Queued chat' } });
    const id = (await created.json()).session.id;
    await page.route('**/agent/queue?*', async route => {
        const session = new URL(route.request().url()).searchParams.get('session_id');
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: session === id ? [{ row_id: -999, agent_id: 'default', thread_id: 99, content: 'Selected queue only' }] : [], pending_steers: [] }) });
    });
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await expect(page.locator('.compose-queue-item')).toContainText('Selected queue only');
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-default').click();
    await expect(page.getByText('Selected queue only', { exact: true })).toHaveCount(0);
});

test('switch requests status for the selected session', async ({ page }) => {
    const seen = [];
    await page.route('**/agents/status?*', async route => {
        seen.push(new URL(route.request().url()).searchParams.get('session_id'));
        await route.fulfill({ contentType: 'application/json', body: '{"active_turns":[],"busy":false}' });
    });
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Scoped status' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await expect.poll(() => seen.includes(id)).toBe(true);
    expect(seen).toContain('default');
});

test('context inspection follows selected chat rather than default', async ({ page }) => {
    const seen = [];
    await page.route('**/agent/context?*', async route => {
        seen.push(new URL(route.request().url()).searchParams.get('session_id'));
        await route.fulfill({ contentType: 'application/json', body: '{"tokens":null,"contextWindow":null,"percent":null}' });
    });
    await page.goto('/');
    const result = await page.request.post('/sessions', { data: { name: 'Context scope' } });
    const id = (await result.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await expect.poll(() => seen.includes(id)).toBe(true);
    expect(seen).toContain('default');
});

test('nondefault model control cannot silently mutate default chat', async ({ page }) => {
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Model guard' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await expect(page.getByRole('button', { name: 'Open model picker', exact: true })).toHaveCount(0);
});

test('selected chat displays only its scoped confirmed model', async ({ page }) => {
    await page.route('**/sessions/*/model-state', async route => {
        const id = new URL(route.request().url()).pathname.split('/')[2];
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(id === 'default' ? { available: false } : { available: true, model: { provider: 'test', id: 'scoped-model', reasoning: true }, thinking_level: 'low' }) });
    });
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Model display' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    const model = page.getByRole('button', { name: 'Open model picker', exact: true });
    await expect(model).toContainText('test/scoped-model');
    await expect(model).toBeDisabled();
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-default').click();
    await expect(page.getByText('test/scoped-model', { exact: true })).toHaveCount(0);
});
