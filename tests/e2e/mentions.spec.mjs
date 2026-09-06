import { test, expect } from '@playwright/test';

test('mention autocomplete inserts stable reference without rerouting send', async ({ page }) => {
    let sent;
    await page.route('**/agent/default/message', async route => { sent = route.request().postDataJSON(); await route.fulfill({ contentType: 'application/json', body: '{"status":"queued"}' }); });
    await page.goto('/');
    const result = await page.request.post('/sessions', { data: { name: 'Mention target' } });
    const id = (await result.json()).session.id;
    const input = page.locator('.compose-input-main textarea');
    await input.fill('@' + id.slice(0, 8));
    await expect(page.getByRole('listbox', { name: 'Session mentions' })).toBeVisible();
    await input.press('Tab');
    await expect(input).toHaveValue('@session:' + id + ' ');
    await input.press('Enter');
    await expect.poll(() => sent?.content).toBe('@session:' + id);
    expect(sent.session_id).toBe('default');
});

test('mention queries reuse registry and preserve text after the caret', async ({ page }) => {
    let requests = 0;
    await page.route('**/sessions?*', async route => {
        if (route.request().method() !== 'GET') return route.continue();
        requests++;
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ sessions: [{ id: 'target', name: 'Target' }] }) });
    });
    await page.goto('/');
    const input = page.locator('.compose-input-main textarea');
    await input.fill('Hello @');
    await expect(page.getByRole('option', { name: /@Target.*target/ })).toBeVisible();
    const before = requests;
    await input.pressSequentially('tar');
    await expect(page.getByRole('option', { name: /@Target.*target/ })).toBeVisible();
    expect(requests).toBe(before);
    await input.press('Escape');
    await expect(page.getByRole('listbox', { name: 'Session mentions' })).toHaveCount(0);
    await input.fill('Hello @t suffix');
    await input.evaluate(el => { el.setSelectionRange(8, 8); el.dispatchEvent(new Event('input', { bubbles: true })); });
    await expect(page.getByRole('option', { name: /@Target.*target/ })).toBeVisible();
    await input.press('Tab');
    await expect(input).toHaveValue('Hello @session:target  suffix');
    await expect.poll(() => input.evaluate(el => el.selectionStart)).toBe(22);
});
