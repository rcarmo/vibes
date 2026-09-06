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
            { id: 'child', name: 'Child', parent_id: 'parent', message_count: 0 },
            { id: 'closed', name: 'Closed', archived: true, message_count: 1 },
        ]} onArchive=${() => { throw new Error('State changed; try again'); }} onDelete=${() => {}} />`, root);
    });
    const fixture = page.locator('#actions-fixture');
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
    await page.getByRole('button', { name: 'New session', exact: true }).click();
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
