import { test, expect } from '@playwright/test';

for (const content of ['> quoted message', '&gt; encoded quoted message']) {
    test(`renders blockquote markdown from ${content.startsWith('&') ? 'encoded' : 'plain'} message text`, async ({ page }) => {
        await page.route('**/timeline?*', route => route.fulfill({ json: {
            posts: [{ id: 92, timestamp: '2026-09-14 20:00:00', data: { type: 'agent_response', content, agent_id: 'default', session_id: 'default' } }],
            has_more: false,
        } }));
        await page.goto('/');
        const quote = page.locator('#post-92 .post-content blockquote');
        await expect(quote).toBeVisible();
        await expect(quote).toContainText('quoted message');
        await expect(quote).toHaveCSS('border-left-style', 'solid');
        await expect(quote).toHaveCSS('border-left-width', '3px');
    });
}
