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
    await page.addInitScript(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => { window.copiedCode = text; } } }));
    const external = [];
    page.on('request', request => { if (request.url().includes('evil.invalid')) external.push(request.url()); });
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 40" onload="alert(1)" style="background:url(https://evil.invalid/root)"><style>text{fill:url(https://evil.invalid/css)}</style><script>alert(2)</script><animate attributeName="opacity" values="0;1"/><foreignObject><iframe src="https://evil.invalid"></iframe></foreignObject><a href="https://evil.invalid"><rect width="120" height="40" fill="#326b82" onclick="alert(3)"/></a><image href="https://evil.invalid/image.png"/><text x="8" y="26">Safe diagram</text></svg>';
    await page.route('**/timeline?*', route => route.fulfill({ json: {
        posts: [{ id: 94, timestamp: '2026-09-14 20:00:00', data: { type: 'agent_response', content: `\`\`\`svg\n${svg}\n\`\`\``, agent_id: 'default', session_id: 'default' } }],
        has_more: false,
    } }));
    await page.goto('/');
    const image = page.locator('#post-94 img.model-inline-svg');
    await expect(image).toBeVisible();
    await expect(image).toHaveAttribute('alt', 'Model-generated SVG diagram');
    const decoded = await image.getAttribute('src').then(src => decodeURIComponent(escape(atob(src.split(',')[1]))));
    expect(decoded).toContain('Safe diagram');
    expect(decoded).not.toMatch(/script|style|foreignObject|iframe|animate|onload|onclick|https:\/\/evil/i);
    expect((await image.boundingBox()).width).toBeGreaterThan(100);
    await expect(page.locator('#post-94 .post-content > svg, #post-94 .post-content a[href*="evil.invalid"]')).toHaveCount(0);
    expect(external).toEqual([]);
    await expect(page.locator('#post-94 code.language-svg')).toContainText('Safe diagram');
    await page.locator('#post-94 pre').hover();
    await page.locator('#post-94 .post-code-copy-btn').click();
    await expect.poll(() => page.evaluate(() => window.copiedCode)).toBe(svg + '\n');
    await page.reload();
    await expect(page.locator('#post-94 img.model-inline-svg')).toBeVisible();
    expect(external).toEqual([]);
});

test('SVG fallback keeps malformed incomplete oversized and over-complex source readable', async ({ page }) => {
    const oversized = `<svg xmlns="http://www.w3.org/2000/svg"><text>${'x'.repeat(64 * 1024 + 1)}</text></svg>`;
    const deep = `<svg xmlns="http://www.w3.org/2000/svg">${'<g>'.repeat(40)}<text>deep</text>${'</g>'.repeat(40)}</svg>`;
    const many = `<svg xmlns="http://www.w3.org/2000/svg">${'<rect/>'.repeat(1001)}</svg>`;
    const content = [`\`\`\`svg\n<svg><broken>\n\`\`\``, `\`\`\`svg\n${oversized}\n\`\`\``, `\`\`\`svg\n${deep}\n\`\`\``, `\`\`\`svg\n${many}\n\`\`\``, `\`\`\`svg\n<svg><text>incomplete`].join('\n');
    await page.route('**/timeline?*', route => route.fulfill({ json: { posts: [{ id: 95, data: { type: 'agent_response', content, session_id: 'default' } }], has_more: false } }));
    await page.goto('/'); const post = page.locator('#post-95');
    await expect(post.locator('.model-inline-svg')).toHaveCount(0);
    await expect(post.locator('.model-inline-svg-error')).toHaveCount(4);
    await expect(post).toContainText('SVG preview unavailable; source retained below.');
    await expect(post).toContainText('<svg><broken>'); await expect(post).toContainText('deep'); await expect(post).toContainText('<svg><text>incomplete');
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
