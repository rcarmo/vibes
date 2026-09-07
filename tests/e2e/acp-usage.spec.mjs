import { test, expect } from '@playwright/test';

// Replay the values actually recorded in the live OpenCode ACP probe; not a live browser-agent run.
const reported = { source: 'acp', tokens: 2949, contextWindow: 262144, percent: 1.1,
    cost: { amount: 0, currency: 'USD' },
    turnUsage: { inputTokens: 773, outputTokens: 35, totalTokens: 3014, thoughtTokens: 30, cachedReadTokens: 2176 }, compactCommand: null };
async function fixture(page, usage) {
    await page.route('**/sessions/*/model-state', route => route.fulfill({ json: {
        available: true, model: { provider: 'opencode', id: 'nemotron-3.5-lightning-free' },
    } }));
    await page.route('**/agent/context?*', route => route.fulfill({ json: typeof usage === 'function' ? usage(route) : usage }));
}
for (const width of [1280, 390]) {
    test(`ACP reported usage at ${width}px`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 844 });
        await fixture(page, reported);
        await page.goto('/');
        const hint = page.locator('.compose-model-usage-hint');
        await expect(hint).toHaveText('USD 0.00');
        await expect(hint).toHaveAttribute('title', /Input: 773.*Output: 35/);
        const gauge = page.getByRole('img', { name: /^Context:/ });
        await expect(gauge).toBeVisible();
        await expect(gauge).toHaveAttribute('title', /Cache read: 2,176/);
        await expect(page.getByRole('button', { name: /Compact context$/ })).toHaveCount(0);
        const bounds = await gauge.boundingBox();
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
        await expect(page.getByText('No messages yet. Start a conversation!', { exact: true })).toBeVisible();
        await page.screenshot({ path: testInfo.outputPath(`acp-usage-${width}.png`) });
    });
}
test('cost-only ACP report survives missing percent; unsupported next session clears it', async ({ page }) => {
    await fixture(page, route => new URL(route.request().url()).searchParams.get('session_id') === 'default'
        ? { ...reported, tokens: null, contextWindow: null, percent: null } : { percent: null, cost: null, turnUsage: null });
    await page.goto('/');
    await expect(page.locator('.compose-model-usage-hint')).toHaveText('USD 0.00');
    await expect(page.getByRole('img', { name: /^Context:/ })).toHaveCount(0);
    const created = await page.request.post('/sessions', { data: { name: 'No reported usage' } });
    const id = (await created.json()).session.id;
    await page.getByTestId('session-switcher').click();
    await page.locator(`#session-option-${id}`).click();
    await expect(page.getByTestId('session-switcher')).toContainText('No reported usage');
    await expect(page.locator('.compose-model-usage-hint')).toHaveCount(0);
});
test('advertised compaction action dispatches scoped intent and preserves draft', async ({ page }) => {
    await fixture(page, { ...reported, compactCommand: '/compact' });
    let payload;
    await page.route('**/agent/default/message', route => {
        payload = route.request().postDataJSON();
        return route.fulfill({ json: { thread_id: 1 } });
    });
    await page.goto('/');
    const draft = page.getByPlaceholder('Message (Enter to send, Shift+Enter for newline)...');
    await draft.fill('Keep this draft');
    const gauge = page.getByRole('button', { name: /Compact context$/ });
    await expect(gauge).toHaveClass(/compose-context-pie/);
    await expect(page.locator('.compose-model-meta-subline button')).toHaveCount(0);
    await gauge.focus();
    await page.keyboard.press('Enter');
    await expect.poll(() => payload?.intent).toBe('compact');
    expect(payload.session_id).toBe('default');
    expect(payload.content).toBe('/compact');
    expect(payload.media_ids).toEqual([]);
    await expect(draft).toHaveValue('Keep this draft');
});
