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
