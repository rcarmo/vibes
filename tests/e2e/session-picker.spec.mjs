import { test, expect } from '@playwright/test';

test('session picker searches, navigates and keeps action buttons separate', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const host = document.createElement('div');
        host.id = 'picker-fixture';
        host.style.cssText = 'position:fixed;inset:0;z-index:9999;background:white;color:black;overflow:auto';
        document.body.appendChild(host);
        window.pickerActions = [];
        render(html`<${SessionPicker} sessions=${[
            { id: 'default', name: 'Default', message_count: 2 },
            { id: 'research', name: 'Research', message_count: 0 },
        ]} onSelect=${id => window.pickerActions.push(['select', id])}
        onRename=${id => window.pickerActions.push(['rename', id])}
        onDelete=${id => window.pickerActions.push(['delete', id])}
        onClose=${() => window.pickerActions.push(['close'])} />`, host);
    });
    const fixture = page.locator('#picker-fixture');
    const input = fixture.getByRole('combobox', { name: 'Search sessions' });
    await expect(input).toBeFocused();
    await expect(fixture.locator('.compose-session-popup-header > label[for="compose-session-search"]')).toHaveText('Search sessions');
    await expect(fixture.locator('.compose-session-popup-header + input')).toHaveAttribute('placeholder', 'Session name or ID');
    await input.fill('Research');
    await expect(fixture.getByRole('option')).toHaveCount(1);
    await input.press('Enter');
    await expect.poll(() => page.evaluate(() => window.pickerActions)).toEqual([['select', 'research']]);
    await fixture.getByRole('button', { name: 'Rename Research' }).focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => page.evaluate(() => window.pickerActions)).toEqual([['select', 'research'], ['rename', 'research']]);
    await input.fill('');
    await input.press('ArrowDown');
    await input.press('Enter');
    await expect.poll(() => page.evaluate(() => window.pickerActions.at(-1))).toEqual(['select', 'research']);
    await input.press('Escape');
    await expect.poll(() => page.evaluate(() => window.pickerActions.at(-1))).toEqual(['close']);
});

test('session search exposes keyboard active option and clears it for no matches', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div'); document.body.append(root);
        render(html`<${SessionPicker} sessions=${[{ id: 'default', name: 'Main' }, { id: 'second', name: 'Second' }]} />`, root);
    });
    const search = page.getByRole('combobox', { name: 'Search sessions' });
    await expect(search).toBeFocused();
    await expect(search).toHaveAttribute('aria-controls', 'session-picker-results');
    await search.press('ArrowDown');
    await expect(search).toHaveAttribute('aria-activedescendant', 'session-option-second');
    await search.press('Home');
    await expect(search).toHaveAttribute('aria-activedescendant', 'session-option-default');
    await search.press('End');
    await expect(search).toHaveAttribute('aria-activedescendant', 'session-option-second');
    await search.fill('unmatched');
    await expect(search).not.toHaveAttribute('aria-activedescendant');
    await expect(page.locator('#session-picker-results [role="option"]')).toHaveCount(0);
    await search.fill('Main');
    await expect(search).toHaveAttribute('aria-activedescendant', 'session-option-default');
});

test('picker gates archive and delete using unfiltered session state', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div'); root.id = 'actions-fixture'; document.body.append(root);
        render(html`<${SessionPicker} sessions=${[
            { id: 'parent', name: 'Parent', message_count: 0, is_running: true },
            { id: 'busy', name: 'Busy', message_count: 0, is_running: true },
            { id: 'child', name: 'Child', parent_id: 'parent', message_count: 0 },
            { id: 'closed', name: 'Closed', archived: true, message_count: 1 },
            ...[undefined, null, '0', -1, 0.5].map((message_count, i) => ({ id: `unknown-${i}`, name: `Unknown ${i}`, message_count })),
        ]} onArchive=${() => { throw new Error('State changed; try again'); }} onDelete=${() => {}} />`, root);
    });
    const fixture = page.locator('#actions-fixture');
    for (let i = 0; i < 5; i++) {
        const button = fixture.getByRole('button', { name: `Delete Unknown ${i}`, exact: true });
        await expect(button).toBeDisabled();
        await expect(button).toHaveAttribute('title', 'Only sessions confirmed empty can be deleted');
    }
    await expect(fixture.getByRole('button', { name: 'Delete Busy', exact: true })).toBeDisabled();
    await expect(fixture.getByRole('button', { name: 'Delete Busy', exact: true })).toHaveAttribute('title', 'Stop the running turn before deleting');
    await expect(fixture.getByRole('button', { name: 'Archive Parent', exact: true })).toBeDisabled();
    await expect(fixture.getByRole('button', { name: 'Delete Parent', exact: true })).toBeDisabled();
    await fixture.getByRole('combobox').fill('Parent');
    await expect(fixture.getByRole('button', { name: 'Delete Parent', exact: true })).toBeDisabled();
    await fixture.getByRole('combobox').fill('');
    await expect(fixture.getByRole('button', { name: 'Delete Child', exact: true })).toBeEnabled();
    await expect(fixture.getByRole('button', { name: 'Delete Closed', exact: true })).toBeDisabled();
    await fixture.getByRole('button', { name: 'Restore Closed', exact: true }).click();
    await expect(fixture.getByRole('alert')).toHaveText('State changed; try again');
});

test('mounted rename dialog validates, saves and restores focus', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('session-switcher').click();
    // Default display name can vary; target the row by stable option ID.
    const row = page.locator('#session-option-default').locator('..');
    const action = row.getByRole('button', { name: /^Rename / });
    await action.click();
    const dialog = page.getByRole('dialog', { name: 'Rename session' });
    const input = dialog.getByRole('textbox', { name: 'Session name' });
    await expect(input).toBeFocused();
    await input.fill('   ');
    await expect(dialog.getByRole('button', { name: 'Save', exact: true })).toBeDisabled();
    await input.fill('Renamed default');
    await dialog.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByTestId('session-switcher')).toContainText('Renamed default');
    await expect(row.getByRole('button', { name: 'Rename Renamed default', exact: true })).toBeFocused();
});

test('create dialog preserves input on server error then creates selected session', async ({ page }) => {
    await page.goto('/');
    let fail = true;
    await page.route('**/sessions', route => {
        if (route.request().method() === 'POST' && fail) {
            fail = false;
            return route.fulfill({ status: 400, contentType: 'application/json', body: '{"error":"Creation rejected"}' });
        }
        return route.continue();
    });
    await page.getByTestId('session-switcher').click();
    await page.getByRole('button', { name: 'New root session…', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'New session' });
    const input = dialog.getByRole('textbox', { name: 'Session name' });
    await expect(input).toBeFocused();
    await expect(dialog.getByRole('button', { name: 'Create', exact: true })).toBeDisabled();
    await input.fill('Created in dialog');
    await dialog.getByRole('button', { name: 'Create', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('Creation rejected');
    await expect(input).toHaveValue('Created in dialog');
    await dialog.getByRole('button', { name: 'Create', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByTestId('session-switcher')).toContainText('Created in dialog');
});

test('delete dialog defaults to cancel and retains backend rejection', async ({ page }) => {
    await page.goto('/');
    const response = await page.request.post('/sessions', { data: { name: 'Delete candidate' } });
    const id = (await response.json()).session.id;
    await page.getByTestId('session-switcher').click();
    const action = page.getByRole('button', { name: 'Delete Delete candidate', exact: true });
    await action.click();
    const dialog = page.getByRole('alertdialog', { name: 'Delete session' });
    await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(action).toBeFocused();
    let reject = true;
    await page.route(`**/sessions/${id}`, route => {
        if (route.request().method() === 'DELETE' && reject) {
            reject = false;
            return route.fulfill({ status: 400, contentType: 'application/json', body: '{"error":"Session now has children"}' });
        }
        return route.continue();
    });
    await action.click();
    await dialog.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('Session now has children');
    await dialog.getByRole('button', { name: 'Delete', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator('#session-option-' + id)).toHaveCount(0);
});

for (const width of [1280, 390]) {
    test(`picker metrics remain distinct and bounded at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 844 });
        await page.goto('/');
        await page.evaluate(async () => {
            const { html, render } = await import('/static/js/vendor/preact-htm.js');
            const { SessionPicker } = await import('/static/js/components/session-picker.js');
            const root = document.createElement('div'); root.id = 'metrics-fixture'; document.body.append(root);
            render(html`<${SessionPicker} sessions=${[
                { id: 'default', name: 'Queued idle chat', queued_count: 2, is_running: false, message_count: 5, last_message_at: '2026-09-06 12:30:00' },
                { id: 'running', name: 'Running chat', queued_count: 0, is_running: true, message_count: 0, last_message_at: 'invalid' },
            ]} />`, root);
        });
        const fixture = page.locator('#metrics-fixture');
        const idle = fixture.locator('#session-option-default');
        await expect(idle.locator('.compose-session-status-pill.idle')).toHaveText('Idle');
        await expect(idle.locator('.queued')).toHaveText('2 queued');
        await expect(idle.locator('time')).toHaveAttribute('datetime', '2026-09-06T12:30:00.000Z');
        await expect(idle.locator('time')).toContainText('Last message:');
        const running = fixture.locator('#session-option-running');
        await expect(running.locator('.compose-session-status-pill.active')).toHaveText('Running');
        await expect(running.locator('time, .queued')).toHaveCount(0);
        const box = await fixture.getByTestId('session-popup').boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
    });
}

test('long session row and lifecycle actions fit narrow picker', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.request.post('/sessions', { data: { name: 'Long session name '.repeat(4) } });
    await page.getByTestId('session-switcher').click();
    const popup = page.getByTestId('session-popup');
    const bounds = await popup.boundingBox();
    const rows = popup.locator('.session-picker-row');
    expect(await rows.count()).toBeGreaterThanOrEqual(2);
    for (const button of await rows.locator('button').all()) {
        const box = await button.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(bounds.x);
        expect(box.x + box.width).toBeLessThanOrEqual(bounds.x + bounds.width + 1);
    }
    await expect(popup.locator('.compose-session-row-main').first()).toBeVisible();
});

test('Alt Enter pins highlighted session without selecting and ignores archived rows', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div'); root.id = 'pin-fixture'; document.body.append(root);
        window.pinActions = [];
        render(html`<${SessionPicker} sessions=${[{ id: 'default', name: 'Main', pinned: true }, { id: 'closed', name: 'Closed', archived: true }]} onPin=${(id, value) => window.pinActions.push(['pin', id, value])} onSelect=${id => window.pinActions.push(['select', id])} />`, root);
    });
    const fixture = page.locator('#pin-fixture');
    const search = fixture.getByRole('combobox');
    await expect(fixture.getByRole('button', { name: 'Unpin session' })).toHaveText('★');
    await search.press('Alt+Enter');
    expect(await page.evaluate(() => window.pinActions)).toEqual([['pin', 'default', false]]);
    await search.fill('Closed');
    await search.press('Alt+Enter');
    expect(await page.evaluate(() => window.pinActions)).toHaveLength(1);
    await expect(fixture.getByRole('button', { name: 'Pin session' })).toBeDisabled();
});

test('picker renders group precedence and announces empty search', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div'); root.id = 'groups-fixture'; document.body.append(root);
        render(html`<${SessionPicker} currentId="current" sessions=${[
            { id: 'parent', name: 'Parent' },
            { id: 'current', name: 'Current', parent_id: 'parent', pinned: true },
            { id: 'pin', name: 'Pinned', pinned: true, is_running: true },
            { id: 'run', name: 'Running', is_running: true },
            { id: 'other', name: 'Other', last_message_at: '2099-01-01T00:00:00Z' },
            { id: 'closed', name: 'Closed', archived: true, pinned: true },
        ]} />`, root);
    });
    const fixture = page.locator('#groups-fixture');
    await expect(fixture.locator('.compose-session-section-heading')).toHaveText(['Current', 'Pinned', 'Active', 'Tree', 'Other', 'Archived']);
    for (const [group, id] of [['Current', 'current'], ['Pinned', 'pin'], ['Active', 'run'], ['Tree', 'parent'], ['Other', 'other'], ['Archived', 'closed']]) {
        await expect(fixture.getByRole('group', { name: group, exact: true }).locator('#session-option-' + id)).toBeVisible();
    }
    await fixture.getByRole('combobox').fill('no-such-session');
    await expect(fixture.getByRole('status')).toHaveText('No matching sessions');
    await expect(fixture.getByRole('group')).toHaveCount(0);
});

for (const width of [1280, 390]) {
    test(`capture mounted session picker at ${width}px`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 844 });
        await page.goto('/');
        await page.request.post('/sessions', { data: { name: 'Visual review session' } });
        await page.getByTestId('session-switcher').click();
        await expect(page.getByTestId('session-popup')).toBeVisible();
        const popup = await page.getByTestId('session-popup').boundingBox();
        if (width === 390) {
            expect(popup.x).toBeCloseTo(8, 0);
            expect(popup.y).toBeCloseTo(8, 0);
            expect(popup.width).toBeCloseTo(374, 0);
            expect(popup.height).toBeCloseTo(828, 0);
        }
        await page.screenshot({ path: testInfo.outputPath(`session-picker-${width}.png`), fullPage: true });
    });
}

test('picker discloses stale registry after polling failure and clears on recovery', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('session-switcher').click();
    const popup = page.getByTestId('session-popup');
    await expect(popup).toBeVisible();
    let fail = true;
    await page.route('**/sessions?*', route => fail
        ? route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"offline"}' })
        : route.continue());
    await expect(popup.getByRole('alert')).toContainText('activity may be stale', { timeout: 10000 });
    await expect(popup.locator('#session-option-default')).toBeVisible();
    fail = false;
    await expect(popup.getByRole('alert')).toHaveCount(0, { timeout: 10000 });
});

test('mounted picker Escape restores trigger and outside click preserves target focus', async ({ page }) => {
    await page.goto('/');
    const trigger = page.getByTestId('session-switcher');
    await trigger.click();
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await page.getByRole('combobox', { name: 'Search sessions' }).press('Escape');
    await expect(page.getByTestId('session-popup')).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await trigger.click();
    await page.evaluate(() => {
        const button = document.createElement('button');
        button.id = 'outside-target'; button.textContent = 'Outside target';
        button.style.cssText = 'position:fixed;bottom:0;left:0;z-index:9999';
        document.body.append(button);
    });
    await page.locator('#outside-target').click();
    await expect(page.getByTestId('session-popup')).toHaveCount(0);
    await expect(page.locator('#outside-target')).toBeFocused();
});

test('picker serializes pending actions and recovers after rejection', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div'); root.id = 'busy-fixture'; document.body.append(root);
        window.actionCalls = 0;
        render(html`<${SessionPicker} sessions=${[{ id: 'default', name: 'Main' }]} onSelect=${() => {
            window.actionCalls++;
            return new Promise((resolve, reject) => { window.rejectAction = reject; });
        }} />`, root);
    });
    const fixture = page.locator('#busy-fixture');
    const search = fixture.getByRole('combobox');
    await search.press('Enter');
    await expect(fixture.getByTestId('session-popup')).toHaveAttribute('aria-busy', 'true');
    await search.press('Enter');
    expect(await page.evaluate(() => window.actionCalls)).toBe(1);
    await page.evaluate(() => window.rejectAction(new Error('Try again')));
    await expect(fixture.getByRole('alert')).toHaveText('Try again');
    await expect(fixture.getByTestId('session-popup')).toHaveAttribute('aria-busy', 'false');
    await search.press('Enter');
    expect(await page.evaluate(() => window.actionCalls)).toBe(2);
    await page.evaluate(() => window.rejectAction(new Error('Done')));
});

test('explicit session picker close control restores trigger focus', async ({ page }) => {
    await page.goto('/');
    const trigger = page.getByTestId('session-switcher');
    await trigger.click();
    await page.getByRole('button', { name: 'Close session picker', exact: true }).click();
    await expect(page.getByTestId('session-popup')).toHaveCount(0);
    await expect(trigger).toBeFocused();
});

test('New branch creates empty child of selected session', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('session-switcher').click();
    await page.getByRole('button', { name: 'New branch', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'New session' });
    await expect(dialog).toContainText('Conversation history is not copied.');
    await dialog.getByRole('textbox', { name: 'Session name' }).fill('Empty child branch');
    await dialog.getByRole('button', { name: 'Create', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByTestId('session-switcher')).toContainText('Empty child branch');
    const registry = await (await page.request.get('/sessions')).json();
    const child = registry.sessions.find(item => item.name === 'Empty child branch');
    expect(child.parent_id).toBe('default');
    expect(child.message_count).toBe(0);
});

test('Rename current footer targets selected chat despite search filter', async ({ page }) => {
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Footer target' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await page.getByTestId('session-switcher').click();
    await page.getByRole('combobox', { name: 'Search sessions' }).fill('no matches');
    await page.getByRole('button', { name: 'Rename current session', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Rename session' });
    await expect(dialog.getByRole('textbox', { name: 'Session name' })).toHaveValue('Footer target');
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
});

test('current selection badge does not imply a running turn', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('session-switcher').click();
    const selected = page.locator('#session-option-default');
    await expect(selected.locator('.compose-session-status-pill.current')).toHaveText('Current');
    await expect(selected.locator('.compose-session-status-pill.idle')).toHaveText('Idle');
    await expect(selected.locator('.compose-session-status-pill.active')).toHaveCount(0);
});

test('mobile current running queued row retains readable name width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div'); root.id = 'crowded-fixture'; document.body.append(root);
        render(html`<${SessionPicker} sessions=${[{ id: 'default', name: 'Current active session with queued work', is_running: true, queued_count: 123, message_count: 99 }]} />`, root);
    });
    const option = page.locator('#crowded-fixture #session-option-default');
    const main = await option.locator('.compose-session-row-main').boundingBox();
    expect(main.width).toBeGreaterThanOrEqual(100);
    const box = await option.boundingBox();
    for (const badge of await option.locator('.compose-session-status-pill').all()) {
        const pill = await badge.boundingBox();
        expect(pill.x + pill.width).toBeLessThanOrEqual(box.x + box.width + 1);
    }
});

test('missing runtime state is unavailable rather than idle', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div'); root.id = 'unknown-state-fixture'; document.body.append(root);
        render(html`<${SessionPicker} sessions=${[{ id: 'default', name: 'Unknown state' }]} />`, root);
    });
    const row = page.locator('#unknown-state-fixture #session-option-default');
    await expect(row.locator('.compose-session-status-pill.unavailable')).toHaveText('Status unavailable');
    await expect(row.locator('.compose-session-status-pill.idle, .compose-session-status-pill.active')).toHaveCount(0);
});

test('mobile picker footer actions remain within popup bounds', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.getByTestId('session-switcher').click();
    const popup = page.getByTestId('session-popup');
    const bounds = await popup.boundingBox();
    for (const name of ['New branch', 'New root session…', 'Rename current session']) {
        const action = popup.getByRole('button', { name, exact: true });
        await expect(action).toBeVisible();
        const box = await action.boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(bounds.x);
        expect(box.x + box.width).toBeLessThanOrEqual(bounds.x + bounds.width + 1);
        expect(box.y + box.height).toBeLessThanOrEqual(bounds.y + bounds.height + 1);
    }
});

test('session dialogs reject duplicate synchronous submit events', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionNameDialog } = await import('/static/js/components/session-name-dialog.js');
        const { SessionDeleteDialog } = await import('/static/js/components/session-delete-dialog.js');
        window.dialogCalls = { save: 0, remove: 0 };
        for (const [name, Component] of [['save', SessionNameDialog], ['remove', SessionDeleteDialog]]) {
            const root = document.createElement('div'); root.id = 'duplicate-' + name; document.body.append(root);
            const action = () => { window.dialogCalls[name]++; return new Promise(() => {}); };
            render(html`<${Component} name="Valid name" onSave=${action} onDelete=${action} onClose=${() => {}} />`, root);
        }
    });
    await page.evaluate(() => {
        for (const form of document.querySelectorAll('[id^="duplicate-"] form')) {
            form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
            form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        }
    });
    expect(await page.evaluate(() => window.dialogCalls)).toEqual({ save: 1, remove: 1 });
});

test('branch dialog retains parent and input when parent is archived before submit', async ({ page }) => {
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Parent archived elsewhere' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await page.getByTestId('session-switcher').click();
    await page.getByRole('button', { name: 'New branch', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'New session' });
    await dialog.getByRole('textbox', { name: 'Session name' }).fill('Must not become root');
    const archived = await page.request.patch('/sessions/' + id, { data: { archived: true } });
    expect(archived.ok()).toBe(true);
    await dialog.getByRole('button', { name: 'Create', exact: true }).click();
    await expect(dialog.getByRole('alert')).toContainText('Restore parent session');
    await expect(dialog.getByRole('textbox', { name: 'Session name' })).toHaveValue('Must not become root');
    const registry = await (await page.request.get('/sessions?include_archived=true')).json();
    expect(registry.sessions.some(item => item.name === 'Must not become root')).toBe(false);
});

test('picker arrows wrap and page navigation clamps by eight entries', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div'); document.body.append(root);
        const sessions = Array.from({ length: 12 }, (_, i) => ({ id: `s${i}`, name: `Session ${String(i).padStart(2, '0')}` }));
        render(html`<${SessionPicker} sessions=${sessions} currentId="s0" />`, root);
    });
    const search = page.getByRole('combobox', { name: 'Search sessions' });
    const ids = await page.locator('#session-picker-results [role="option"]').evaluateAll(nodes => nodes.map(node => node.id));
    await search.press('PageDown');
    await expect(search).toHaveAttribute('aria-activedescendant', ids[8]);
    await search.press('PageDown');
    await expect(search).toHaveAttribute('aria-activedescendant', ids[11]);
    await search.press('ArrowDown');
    await expect(search).toHaveAttribute('aria-activedescendant', ids[0]);
    await search.press('ArrowUp');
    await expect(search).toHaveAttribute('aria-activedescendant', ids[11]);
    await search.press('PageUp');
    await expect(search).toHaveAttribute('aria-activedescendant', ids[3]);
    await search.press('PageUp');
    await expect(search).toHaveAttribute('aria-activedescendant', ids[0]);
    await search.fill('no matching session');
    await search.press('PageDown');
    await search.press('ArrowUp');
    await expect(search).not.toHaveAttribute('aria-activedescendant', /.+/);
});

test('picker search Tab selects while composition and reverse Tab do not', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div'); document.body.append(root);
        window.tabSelections = [];
        render(html`<${SessionPicker} sessions=${[{ id: 'default', name: 'Main' }, { id: 'second', name: 'Second' }]} onSelect=${id => window.tabSelections.push(id)} />`, root);
    });
    const search = page.getByRole('combobox', { name: 'Search sessions' });
    await search.evaluate(node => {
        node.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, isComposing: true }));
        node.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, isComposing: true }));
    });
    await expect(search).toHaveAttribute('aria-activedescendant', 'session-option-default');
    expect(await page.evaluate(() => window.tabSelections)).toEqual([]);
    await search.press('Shift+Tab');
    expect(await page.evaluate(() => window.tabSelections)).toEqual([]);
    await search.focus();
    await search.press('ArrowDown');
    await search.press('Tab');
    await expect.poll(() => page.evaluate(() => window.tabSelections)).toEqual(['second']);
    await search.fill('no matches');
    await search.press('Tab');
    await expect(search).not.toBeFocused();
    expect(await page.evaluate(() => window.tabSelections)).toEqual(['second']);
});

test('non-search typeahead selects labels without changing search text', async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-09-06T12:00:00Z'));
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div'); document.body.append(root);
        render(html`<${SessionPicker} sessions=${[{ id: 'default', name: 'Main' }, { id: 'beta', name: 'Beta' }, { id: 'bravo', name: 'Bravo' }]} />`, root);
    });
    const popup = page.getByTestId('session-popup');
    const search = page.getByRole('combobox', { name: 'Search sessions' });
    await popup.focus();
    await popup.press('b');
    await expect(search).toHaveAttribute('aria-activedescendant', 'session-option-beta');
    await popup.press('r');
    await expect(search).toHaveAttribute('aria-activedescendant', 'session-option-bravo');
    await expect(search).toHaveValue('');
    // At exactly 700ms the prefix remains live: "brm" has no match.
    await page.clock.setFixedTime(new Date('2026-09-06T12:00:00.700Z'));
    await popup.press('m');
    await expect(search).toHaveAttribute('aria-activedescendant', 'session-option-bravo');
    // More than 700ms after the last key starts a fresh "m" query.
    await page.clock.setFixedTime(new Date('2026-09-06T12:00:01.401Z'));
    await popup.press('m');
    await expect(search).toHaveAttribute('aria-activedescendant', 'session-option-default');
    await popup.press('Home');
    await popup.press('m');
    await expect(search).toHaveAttribute('aria-activedescendant', 'session-option-default');
    await search.fill('Beta');
    await expect(search).toHaveValue('Beta');
    await expect(page.locator('#session-picker-results [role="option"]')).toHaveCount(1);
});

test('picker disables mutation controls when callbacks are unavailable', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { SessionPicker } = await import('/static/js/components/session-picker.js');
        const root = document.createElement('div');
        root.id = 'readonly-picker';
        document.body.appendChild(root);
        render(html`<${SessionPicker} sessions=${[{ id: 'empty', name: 'Read only', message_count: 0 }, { id: 'unknown', name: 'Unknown history' }]} />`, root);
    });
    const picker = page.locator('#readonly-picker');
    await expect(picker.locator('#session-option-empty')).toContainText('0 messages');
    await expect(picker.locator('#session-option-unknown')).toContainText('Message count unavailable');
    for (const name of ['Rename Read only', 'Delete Read only', 'New root session…']) {
        await expect(picker.getByRole('button', { name, exact: true })).toBeDisabled();
    }
    const pins = picker.getByRole('button', { name: 'Pin session', exact: true });
    await expect(pins).toHaveCount(2);
    await expect(pins.nth(0)).toBeDisabled();
    await expect(pins.nth(1)).toBeDisabled();
    await expect(picker.getByRole('button', { name: 'Archive Read only', exact: true })).toHaveCount(0);
});

test('canonical ID stays searchable and described without a metadata row', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('session-switcher').click();
    await page.getByRole('combobox', { name: 'Search sessions', exact: true }).fill('default');
    const option = page.locator('#session-option-default');
    await expect(option).toBeVisible();
    await expect(option).toHaveAccessibleDescription('Session ID: default');
    await expect(option).toHaveAttribute('title', 'Session ID: default');
    await expect(option.locator('.compose-session-row-meta').filter({ hasText: /^default$/ })).toHaveCount(0);
});
