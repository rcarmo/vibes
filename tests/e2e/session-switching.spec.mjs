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
