import { test, expect } from '@playwright/test';

test('blocked popup preserves editor tab', async ({ page }) => {
    await page.goto('/?editor=README.md');
    await expect(page.locator('.cm-editor')).toBeVisible();
    await page.evaluate(() => { window.open = () => null; });
    const tab = page.locator('.tab-item', { hasText: 'README.md' });
    await tab.click({ button: 'right' });
    await page.locator('.tab-context-menu button', { hasText: 'Open in Window' }).click();
    await expect(tab).toBeVisible();
    await expect(page.locator('.cm-editor')).toBeVisible();
});
