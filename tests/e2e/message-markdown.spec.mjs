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

test('renders fenced SVG inline as a sanitized inert image', async ({ page }) => {
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40" onload="alert(1)"><script>alert(2)</script><foreignObject><iframe src="https://evil.invalid"></iframe></foreignObject><a href="https://evil.invalid"><rect width="120" height="40" fill="#326b82" onclick="alert(3)"/></a><text x="8" y="26">Safe diagram</text></svg>';
    await page.route('**/timeline?*', route => route.fulfill({ json: {
        posts: [{ id: 94, timestamp: '2026-09-14 20:00:00', data: { type: 'agent_response', content: `\`\`\`svg\n${svg}\n\`\`\``, agent_id: 'default', session_id: 'default' } }],
        has_more: false,
    } }));
    await page.goto('/');
    const image = page.locator('#post-94 img.model-inline-svg');
    await expect(image).toBeVisible();
    await expect(image).toHaveAttribute('alt', 'Model-generated SVG');
    const decoded = await image.getAttribute('src').then(src => decodeURIComponent(escape(atob(src.split(',')[1]))));
    expect(decoded).toContain('Safe diagram');
    expect(decoded).not.toMatch(/script|foreignObject|iframe|onload|onclick|https:\/\/evil/i);
    expect((await image.boundingBox()).width).toBeGreaterThan(100);
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
