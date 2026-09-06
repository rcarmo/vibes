import { test, expect } from '@playwright/test';

for (const [key, mode] of [['Enter', 'auto'], ['Control+Enter', 'steer'], ['Meta+Enter', 'steer']]) {
    test(`composer ${key} submits ${mode}`, async ({ page }) => {
        let payload;
        await page.route('**/agent/default/message', async route => {
            payload = route.request().postDataJSON();
            await route.fulfill({ contentType: 'application/json', body: '{"status":"queued"}' });
        });
        await page.goto('/');
        const input = page.locator('.compose-input-main textarea');
        await input.fill('mode verification');
        await input.press(key);
        await expect.poll(() => payload?.mode).toBe(mode);
        expect(payload.content).toBe('mode verification');
        await expect(input).toHaveValue('');
    });
}
