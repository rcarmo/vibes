import { test, expect } from '@playwright/test';

test('message action bar copies original text and preserves delete control', async ({ page }) => {
    await page.addInitScript(() => {
        window.copiedText = null;
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => { window.copiedText = text; } } });
    });
    const content = 'Copy **the original** message text.';
    await page.route('**/timeline?*', route => route.fulfill({ json: {
        posts: [{ id: 91, timestamp: '2026-09-14 20:00:00', data: { type: 'agent_response', content, agent_id: 'default', session_id: 'default' } }],
        has_more: false,
    } }));
    await page.goto('/');
    const post = page.locator('#post-91');
    await post.hover();
    const copy = post.getByRole('button', { name: 'Copy message' });
    await expect(copy).toBeVisible();
    await expect(post.getByRole('button', { name: 'Delete message' })).toBeVisible();
    await copy.click();
    await expect.poll(() => page.evaluate(() => window.copiedText)).toBe(content);
    await expect(post.getByRole('button', { name: 'Copied' })).toBeVisible();
});
