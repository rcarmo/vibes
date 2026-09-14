import { test, expect } from '@playwright/test';

// Real HTTP requests, no component mount or mocked asset response.
test('reload uses paired content-versioned assets and keeps the desktop picker anchored', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const assets = [];
    page.on('response', response => {
        if (/\/static\/dist\/app\.(js|css)\?/.test(response.url())) assets.push(response);
    });
    for (let pass = 0; pass < 2; pass++) {
        assets.length = 0;
        const navigation = pass === 0 ? await page.goto('/') : await page.reload();
        expect(navigation.headers()['cache-control']).toBe('no-store');
        await expect(page.getByTestId('session-switcher')).toBeVisible();
        await expect.poll(() => assets.length).toBe(2);
        const versions = assets.map(response => new URL(response.url()).searchParams.get('v'));
        expect(versions[0]).toMatch(/^[0-9a-f]{16}$/);
        expect(versions[1]).toBe(versions[0]);
        for (const asset of assets) {
            expect(await asset.headerValue('cache-control')).toBe('no-cache, must-revalidate');
        }
        await page.getByTestId('session-switcher').click();
        const picker = page.locator('.compose-input-wrapper > .compose-session-popup');
        await expect(picker).toBeVisible();
        await expect(picker).toHaveCSS('position', 'absolute');
        const popup = await picker.boundingBox();
        const composer = await page.locator('.compose-input-wrapper').boundingBox();
        expect(popup.y).toBeGreaterThan(0);
        expect(popup.y + popup.height).toBeLessThanOrEqual(composer.y - 5);
        expect(Math.abs(popup.x - composer.x)).toBeLessThanOrEqual(1);
        expect(Math.abs(popup.width - composer.width)).toBeLessThanOrEqual(2);
        await page.getByRole('combobox', { name: 'Search sessions' }).press('Escape');
        await expect(page.getByTestId('session-switcher')).toBeFocused();
    }
});
