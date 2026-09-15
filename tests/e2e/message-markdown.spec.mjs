import { test, expect } from '@playwright/test';

test('fenced syntax colours preserve literal text, escaping and code-copy output', async ({ page }) => {
    const source = 'const ready = true;\nconsole.log("<img src=x onerror=alert(1)>");\n';
    const content = '```js\n' + source + '```\n\n```unknown\n<img src=x onerror=alert(1)>\n```';
    await page.addInitScript(() => {
        window.copiedCode = '';
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
            writeText: async text => { window.copiedCode = text; },
        } });
    });
    await page.route('**/timeline?*', route => route.fulfill({ json: {
        posts: [{ id: 93, timestamp: '2026-09-14 20:00:00', data: { type: 'agent_response', content, agent_id: 'default', session_id: 'default' } }],
        has_more: false,
    } }));
    await page.goto('/');
    const post = page.locator('#post-93');
    await expect(post.locator('code.language-js .tok-keyword')).toHaveText('const');
    await expect(post.locator('code.language-js .tok-bool')).toHaveText('true');
    expect(await post.locator('code.language-js').textContent()).toBe(source);
    await expect(post.locator('pre img, pre script')).toHaveCount(0);
    await expect(post.locator('code.language-unknown')).toHaveText('<img src=x onerror=alert(1)>\n');
    await expect(post.locator('code.language-unknown span')).toHaveCount(0);
    await post.locator('pre').first().hover();
    await post.locator('.post-code-copy-btn').first().click();
    expect(await page.evaluate(() => window.copiedCode)).toBe(source);
});

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
