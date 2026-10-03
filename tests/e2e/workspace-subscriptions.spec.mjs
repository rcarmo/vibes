import { test, expect } from '@playwright/test';

test('workspace subscriptions are independent and reconnect in portrait', async ({ browser }) => {
    const first = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const second = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const a = await first.newPage();
    const b = await second.newPage();
    const requests = [[], []];
    for (const [index, page] of [a, b].entries()) {
        await page.route('**/workspace/visibility', async route => {
            requests[index].push(route.request().postDataJSON());
            await route.fulfill({ contentType: 'application/json', body: '{"ok":true}' });
        });
        await page.goto('/');
        const sidebar = page.locator('.workspace-sidebar');
        if (!await sidebar.isVisible()) {
            await page.getByTestId('hamburger').click();
            await page.getByRole('menuitem', { name: 'Show workspace', exact: true }).click();
        }
        await expect(sidebar).toBeVisible();
        await expect.poll(() => requests[index].some(item => item.visible)).toBe(true);
    }
    expect(requests[0].find(item => item.visible).subscription_id).not.toBe(requests[1].find(item => item.visible).subscription_id);
    const before = requests[0].length;
    await a.evaluate(() => window.dispatchEvent(new CustomEvent('workspace-reconnected')));
    await expect.poll(() => requests[0].length).toBeGreaterThan(before);
    expect(requests[0].at(-1).visible).toBe(true);
    await first.close();
    await second.close();
});
