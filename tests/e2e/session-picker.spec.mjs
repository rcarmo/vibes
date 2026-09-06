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
    const input = fixture.getByRole('searchbox', { name: 'Search sessions' });
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
