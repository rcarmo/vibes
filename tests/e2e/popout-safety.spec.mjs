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

test('transferred unsaved content stays dirty and prompts before closing', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => {
        localStorage.setItem('vibes:editor-popout:unsaved-test', JSON.stringify({
            path: 'README.md', content: 'unsaved revision', savedContent: 'original', capturedAt: Date.now(),
        }));
    });
    await page.goto('/?editor=README.md&editor_popout=unsaved-test');
    await expect(page.locator('.cm-editor')).toContainText('unsaved revision');
    await expect(page.locator('.tab-item.dirty')).toBeVisible();
    let prompted = false;
    page.on('dialog', async dialog => { prompted = true; await dialog.dismiss(); });
    await page.locator('.tab-close').click();
    expect(prompted).toBe(true);
    await expect(page.locator('.tab-item')).toBeVisible();
});
