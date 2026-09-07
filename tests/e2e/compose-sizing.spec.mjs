import { test, expect } from '@playwright/test';
const message = page => page.getByPlaceholder('Message (Enter to send, Shift+Enter for newline)...');

for (const width of [1280, 390]) {
    test(`in-composer pill and drag height at ${width}px`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 844 });
        await page.route('**/sessions/*/model-state', route => route.fulfill({ json: { available: true, model: { provider: 'opencode', id: 'nemotron-3.5-lightning-free' } } }));
        // Recorded live ACP values, replayed for a stable visual fixture.
        await page.route('**/agent/context?*', route => route.fulfill({ json: { tokens: 2949, contextWindow: 262144, percent: 1.1, cost: { amount: 0, currency: 'USD' } } }));
        await page.goto('/');
        const pill = page.getByTestId('session-switcher');
        await expect(page.locator('.compose-input-wrapper > .compose-session-trigger-top').getByTestId('session-switcher')).toHaveText('@default');
        await expect(pill).toHaveClass(/compose-session-trigger-pill/);
        await expect(page.getByText('No messages yet. Start a conversation!', { exact: true })).toBeVisible();
        const box = page.getByTestId('compose-box');
        const grip = box.getByRole('separator', { name: 'Resize input' });
        const input = message(page);
        await input.fill('Draft retained while resizing.\nSession selection stays inside the composer.');
        const before = await input.boundingBox();
        const handle = await grip.boundingBox();
        await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2);
        await page.mouse.down();
        await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2 - 140, { steps: 8 });
        await page.mouse.up();
        await expect.poll(async () => (await input.boundingBox()).height).toBeCloseTo(before.height + 140, 0);
        const grown = (await input.boundingBox()).height;
        expect(await page.evaluate(() => document.body.style.cursor)).toBe('');
        expect(await page.evaluate(() => Number(localStorage.getItem('piclaw_compose_height')))).toBeCloseTo(grown, 0);
        const pillBounds = await pill.boundingBox();
        const wrapper = await page.locator('.compose-input-wrapper').boundingBox();
        expect(pillBounds.x).toBeGreaterThanOrEqual(wrapper.x);
        expect(pillBounds.x + pillBounds.width).toBeLessThanOrEqual(wrapper.x + wrapper.width);
        await expect(page.locator('.compose-model-usage-hint')).toHaveText('USD 0.00');
        await page.screenshot({ path: testInfo.outputPath(`composer-pill-resized-${width}.png`) });
        await pill.click();
        await page.getByRole('combobox', { name: 'Search sessions' }).press('Escape');
        await expect(pill).toBeFocused();
        await page.reload();
        await expect.poll(async () => (await input.boundingBox()).height).toBeCloseTo(grown, 0);
        await expect(input).toHaveValue('Draft retained while resizing.\nSession selection stays inside the composer.');
        await page.setViewportSize({ width, height: 400 });
        await expect.poll(async () => (await input.boundingBox()).height).toBeLessThanOrEqual(200);
    });
}
test('resize keyboard limits and unmount cleanup across session switch', async ({ page }) => {
    await page.goto('/');
    const grip = page.getByRole('separator', { name: 'Resize input' });
    await grip.focus();
    await page.keyboard.press('End');
    const max = Number(await grip.getAttribute('aria-valuemax'));
    await expect.poll(async () => (await message(page).boundingBox()).height).toBe(max);
    await page.keyboard.press('Home');
    const min = Number(await grip.getAttribute('aria-valuemin'));
    await expect.poll(async () => (await message(page).boundingBox()).height).toBe(min);
    const created = await page.request.post('/sessions', { data: { name: 'Resize destination' } });
    expect(created.ok()).toBe(true);
    const handle = await grip.boundingBox();
    await page.mouse.move(handle.x + handle.width / 2, handle.y + 7);
    await page.mouse.down();
    // Keyboard opens the picker while the resize pointer is still captured.
    await page.getByTestId('session-switcher').focus();
    await page.keyboard.press('Enter');
    const search = page.getByRole('combobox', { name: 'Search sessions' });
    await search.fill('Resize destination');
    await search.press('Enter');
    await expect(page.getByTestId('session-switcher')).toContainText('Resize destination');
    expect(await page.evaluate(() => document.body.style.cursor)).toBe('');
    expect(await page.evaluate(() => document.body.style.userSelect)).toBe('');
    await page.mouse.up();
});
