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
    await expect(model).toBeEnabled();
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-default').click();
    await expect(page.getByText('test/scoped-model', { exact: true })).toHaveCount(0);
});

test('nondefault model selection uses scoped mutation endpoint', async ({ page }) => {
    await page.route('**/sessions/*/model-state', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"model":{"provider":"test","id":"old"}}' }));
    await page.route('**/sessions/*/models', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"models":[{"provider":"test","id":"new"}],"thinking_levels":["off"]}' }));
    let path;
    await page.route('**/sessions/*/model', async route => {
        path = new URL(route.request().url()).pathname;
        expect(route.request().postDataJSON()).toEqual({ provider: 'test', model_id: 'new' });
        await route.fulfill({ contentType: 'application/json', body: '{"model":{"provider":"test","id":"new"},"thinking_level":"off"}' });
    });
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Change model' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await page.getByRole('button', { name: 'Open model picker', exact: true }).click();
    await page.getByRole('menuitem', { name: 'test/new', exact: true }).click();
    await expect.poll(() => path).toBe(`/sessions/${id}/model`);
});

test('nondefault thinking cycle uses supported scoped levels', async ({ page }) => {
    await page.route('**/sessions/*/model-state', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"model":{"provider":"test","id":"reasoner","reasoning":true},"thinking_level":"off"}' }));
    await page.route('**/sessions/*/models', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"models":[],"thinking_levels":["off","low"]}' }));
    let payload, path;
    await page.route('**/sessions/*/model', async route => {
        payload = route.request().postDataJSON();
        path = new URL(route.request().url()).pathname;
        await route.fulfill({ contentType: 'application/json', body: '{"model":{"provider":"test","id":"reasoner","reasoning":true},"thinking_level":"low"}' });
    });
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Thinking change' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await page.getByRole('button', { name: 'Cycle thinking level', exact: true }).click();
    await expect.poll(() => payload?.thinking_level).toBe('low');
    expect(path).toBe(`/sessions/${id}/model`);
});

test('model catalog errors are visible and closing discards late responses', async ({ page }) => {
    await page.route('**/sessions/*/model-state', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"model":{"provider":"test","id":"old"}}' }));
    let release;
    let calls = 0;
    await page.route('**/sessions/*/models', async route => {
        calls++;
        if (calls === 1) {
            await new Promise(resolve => { release = resolve; });
            await route.fulfill({ contentType: 'application/json', body: '{"available":true,"models":[{"provider":"test","id":"stale"}]}' });
        } else {
            await route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"Catalog unavailable"}' });
        }
    });
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Catalog race' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    const toggle = page.getByRole('button', { name: 'Open model picker', exact: true });
    await toggle.click();
    await expect.poll(() => !!release).toBe(true);
    await toggle.click();
    await toggle.click();
    await expect(page.locator('.compose-model-popup [role="alert"]')).toContainText('Catalog unavailable');
    release();
    await expect(page.getByRole('menuitem', { name: 'test/stale', exact: true })).toHaveCount(0);
});

test('model catalog retry recovers and search filters selectable choices', async ({ page }) => {
    await page.route('**/sessions/*/model-state', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"model":{"provider":"test","id":"old"}}' }));
    let calls = 0;
    await page.route('**/sessions/*/models', route => {
        calls++;
        return route.fulfill(calls === 1
            ? { status: 503, contentType: 'application/json', body: '{"error":"Temporary failure"}' }
            : { contentType: 'application/json', body: '{"available":true,"models":[{"provider":"test","id":"alpha"},{"provider":"test","id":"beta"}]}' });
    });
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Search models' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await page.getByRole('button', { name: 'Open model picker', exact: true }).click();
    await page.getByRole('button', { name: 'Retry model catalog', exact: true }).click();
    await expect(page.getByRole('menuitem', { name: 'test/alpha', exact: true })).toBeVisible();
    const search = page.getByRole('searchbox', { name: 'Search models' });
    await search.fill('BETA');
    await expect(page.getByRole('menuitem', { name: 'test/alpha', exact: true })).toHaveCount(0);
    await expect(page.getByRole('menuitem', { name: 'test/beta', exact: true })).toBeVisible();
    await search.fill('missing');
    await expect(page.getByText('No matching models', { exact: true })).toBeVisible();
});

test('model picker keyboard navigation focuses choices and Escape restores trigger', async ({ page }) => {
    await page.route('**/sessions/*/model-state', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"model":{"provider":"test","id":"old"}}' }));
    await page.route('**/sessions/*/models', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"models":[{"provider":"test","id":"alpha"},{"provider":"test","id":"beta"}]}' }));
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Keyboard models' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    const trigger = page.getByRole('button', { name: 'Open model picker', exact: true });
    await trigger.click();
    const search = page.getByRole('searchbox', { name: 'Search models' });
    await expect(search).toBeFocused();
    await expect(page.getByRole('menuitem', { name: 'test/alpha', exact: true })).toBeVisible();
    await search.press('ArrowDown');
    await expect(page.getByRole('menuitem', { name: 'test/alpha', exact: true })).toBeFocused();
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('menuitem', { name: 'test/beta', exact: true })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(search).toHaveCount(0);
    await expect(trigger).toBeFocused();
});

test('Next model cycles scoped catalog without default commands', async ({ page }) => {
    await page.route('**/sessions/*/model-state', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"model":{"provider":"test","id":"alpha"}}' }));
    await page.route('**/sessions/*/models', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"models":[{"provider":"test","id":"alpha"},{"provider":"test","id":"beta"}]}' }));
    let mutation, commandCount = 0;
    await page.route('**/agent/default/message', route => { commandCount++; return route.fulfill({ contentType: 'application/json', body: '{}' }); });
    await page.route('**/sessions/*/model', route => {
        mutation = { path: new URL(route.request().url()).pathname, data: route.request().postDataJSON() };
        return route.fulfill({ contentType: 'application/json', body: '{"model":{"provider":"test","id":"beta"}}' });
    });
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Cycle models' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await page.getByRole('button', { name: 'Open model picker', exact: true }).click();
    await page.getByRole('button', { name: 'Next model', exact: true }).click();
    await expect.poll(() => mutation).toEqual({ path: `/sessions/${id}/model`, data: { provider: 'test', model_id: 'beta' } });
    expect(commandCount).toBe(0);
});

test('late model mutation cannot relabel a newly selected chat', async ({ page }) => {
    await page.route('**/sessions/*/model-state', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"model":{"provider":"test","id":"own"}}' }));
    await page.route('**/sessions/*/models', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"models":[{"provider":"test","id":"late"}]}' }));
    let release;
    const completed = new Promise(resolve => {
        page.route('**/sessions/*/model', async route => {
            await new Promise(done => { release = done; });
            await route.fulfill({ contentType: 'application/json', body: '{"model":{"provider":"test","id":"late"}}' });
            resolve();
        });
    });
    await page.goto('/');
    const first = (await (await page.request.post('/sessions', { data: { name: 'First mutation' } })).json()).session.id;
    const second = (await (await page.request.post('/sessions', { data: { name: 'Second mutation' } })).json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + first).click();
    await page.getByRole('button', { name: 'Open model picker', exact: true }).click();
    await page.getByRole('menuitem', { name: 'test/late', exact: true }).click();
    await expect.poll(() => !!release).toBe(true);
    await page.keyboard.press('Escape');
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + second).click();
    const label = page.getByRole('button', { name: 'Open model picker', exact: true });
    await expect(label).toContainText('own');
    release(); await completed;
    // Drain browser work after the response, including the old promise continuation.
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(label).toContainText('own');
});

test('default composer model controls use scoped mutation, not slash messages', async ({ page }) => {
    await page.route('**/sessions/default/model-state', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"model":{"provider":"test","id":"alpha","reasoning":true},"thinking_level":"off"}' }));
    await page.route('**/sessions/default/models', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"models":[{"provider":"test","id":"beta"}],"thinking_levels":["off","low"]}' }));
    const changes = [];
    let commands = 0;
    await page.route('**/agent/default/message', route => { commands++; return route.fulfill({ contentType: 'application/json', body: '{}' }); });
    await page.route('**/sessions/default/model', route => {
        changes.push(route.request().postDataJSON());
        return route.fulfill({ contentType: 'application/json', body: '{"model":{"provider":"test","id":"beta","reasoning":true},"thinking_level":"off"}' });
    });
    await page.goto('/');
    await page.getByRole('button', { name: 'Open model picker', exact: true }).click();
    await page.getByRole('menuitem', { name: 'test/beta', exact: true }).click();
    await page.getByRole('button', { name: 'Cycle thinking level', exact: true }).click();
    await expect.poll(() => changes).toEqual([{ provider: 'test', model_id: 'beta' }, { thinking_level: 'low' }]);
    expect(commands).toBe(0);
});

test('context gauge hides invalid percent and exposes accessible valid usage', async ({ page }) => {
    let context = { percent: 'invalid', tokens: 10, contextWindow: 100 };
    await page.route('**/agent/context?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(context) }));
    await page.goto('/');
    await expect(page.locator('.compose-input-main textarea')).toBeVisible();
    await expect(page.locator('.compose-context-pie')).toHaveCount(0);
    context = { percent: 25, tokens: 1000, contextWindow: 4000 };
    await page.reload();
    await expect(page.getByRole('img', { name: /Context:.*25%/ })).toBeVisible();
});

test('compaction indicator requires explicit selected-session confirmation', async ({ page }) => {
    await page.route('**/sessions/*/model-state', route => {
        const active = new URL(route.request().url()).pathname === '/sessions/default/model-state';
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ available: active, compacting: active ? true : null, model: null }) });
    });
    await page.goto('/');
    await expect(page.getByText('Compacting context…', { exact: true })).toBeVisible();
    const created = await page.request.post('/sessions', { data: { name: 'No compaction state' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await expect(page.getByText('Compacting context…', { exact: true })).toHaveCount(0);
});

test('switching chats during thinking catalog lookup prevents late mutation', async ({ page }) => {
    await page.route('**/sessions/*/model-state', route => route.fulfill({ contentType: 'application/json', body: '{"available":true,"model":{"provider":"test","id":"reasoner","reasoning":true},"thinking_level":"off"}' }));
    let release;
    let finish;
    const finished = new Promise(resolve => { finish = resolve; });
    await page.route('**/sessions/*/models', async route => {
        await new Promise(resolve => { release = resolve; });
        await route.fulfill({ contentType: 'application/json', body: '{"available":true,"models":[],"thinking_levels":["off","low"]}' });
        finish();
    });
    let mutations = 0;
    await page.route('**/sessions/*/model', route => { mutations++; return route.fulfill({ contentType: 'application/json', body: '{}' }); });
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Thinking lookup switch' } });
    const id = (await created.json()).session.id;
    await page.getByRole('button', { name: 'Cycle thinking level', exact: true }).click();
    await expect.poll(() => !!release).toBe(true);
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await expect(page.getByTestId('session-switcher')).toContainText('Thinking lookup switch');
    release(); await finished;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    expect(mutations).toBe(0);
});

test('context inspection refreshes periodically and clears unavailable usage', async ({ page }) => {
    let unavailable = false;
    let count = 0;
    await page.route('**/agent/context?*', route => {
        count++;
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(!unavailable ? { percent: 25, tokens: 1000, contextWindow: 4000 } : { percent: null }) });
    });
    await page.goto('/');
    await expect(page.locator('.compose-context-pie')).toBeVisible();
    unavailable = true;
    const before = count;
    await expect.poll(() => count, { timeout: 20000 }).toBeGreaterThan(before);
    await expect(page.locator('.compose-context-pie')).toHaveCount(0);
});

test('context refresh follows completion of held model inspection', async ({ page }) => {
    let release, held = false, contextAfterModel = false;
    await page.route('**/sessions/*/model-state', async route => {
        held = true;
        await new Promise(resolve => { release = resolve; });
        held = false;
        await route.fulfill({ contentType: 'application/json', body: '{"available":false}' });
    });
    await page.route('**/agent/context?*', route => {
        // Reconnect has its own refresh; assert the ordered request after release
        // by tracking it separately below rather than inferring server locks.
        if (!held) contextAfterModel = true;
        return route.fulfill({ contentType: 'application/json', body: '{"percent":25}' });
    });
    await page.goto('/');
    await expect.poll(() => !!release).toBe(true);
    release();
    await expect.poll(() => contextAfterModel).toBe(true);
    await expect(page.locator('.compose-context-pie')).toBeVisible();
});
