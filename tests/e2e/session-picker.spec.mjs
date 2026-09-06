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
