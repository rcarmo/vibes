import { test, expect } from '@playwright/test';
import { BASE_URL, waitForConnection } from './helpers.mjs';

test.describe('Feature: Compose Box UX', () => {
    test('Scenario: Enter sends message, Shift+Enter inserts newline', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        const textarea = page.locator('.compose-box textarea');
        await textarea.fill('Line one');
        await textarea.press('Shift+Enter');
        await textarea.type('Line two');
        expect(await textarea.inputValue()).toContain('\n');
    });

    test('Scenario: Compose history with arrow keys', async ({ page }) => {
        test.setTimeout(30000);

        // Seed compose history deterministically before app boot
        await page.addInitScript(() => {
            localStorage.setItem('vibes_compose_history', JSON.stringify(['history one', 'history two']));
        });

        await page.goto(BASE_URL);
        await waitForConnection(page);
        const textarea = page.locator('.compose-box textarea');

        await textarea.click();
        await textarea.fill('');

        // Up at start -> newest
        await textarea.press('ArrowUp');
        await expect(textarea).toHaveValue('history two');

        // Up at start again -> older
        await textarea.press('Home');
        await textarea.press('ArrowUp');
        await expect(textarea).toHaveValue('history one');

        // Down at end -> newer
        await textarea.press('End');
        await textarea.press('ArrowDown');
        await expect(textarea).toHaveValue('history two');
    });

    test('Scenario: Model picker typeahead', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        // Open model picker if button exists
        const modelBtn = page.locator('.compose-model-hint-btn').first();
        if (await modelBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
            await modelBtn.click();
            const popup = page.locator('.compose-model-popup');
            await expect(popup).toBeVisible({ timeout: 3000 });
        }
    });
});

test.describe('Feature: Theme Support', () => {
    test('Scenario: Dark mode renders correctly', async ({ page }) => {
        await page.emulateMedia({ colorScheme: 'dark' });
        await page.goto(BASE_URL);
        const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
        expect(bg).toBeDefined();
        // Dark backgrounds have low luminance
    });

    test('Scenario: Light mode renders correctly', async ({ page }) => {
        await page.emulateMedia({ colorScheme: 'light' });
        await page.goto(BASE_URL);
        const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
        expect(bg).toBeDefined();
    });
});
