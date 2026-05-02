import { test, expect } from '@playwright/test';
import { BASE_URL, waitForConnection } from './helpers.mjs';

test.describe('Feature: Page Load and Connection', () => {
    test('Scenario: SPA loads with correct title', async ({ page }) => {
        await page.goto(BASE_URL);
        await expect(page).toHaveTitle(/Vibes/);
    });

    test('Scenario: Compose box is visible on load', async ({ page }) => {
        await page.goto(BASE_URL);
        await expect(page.locator('.compose-box')).toBeVisible();
        await expect(page.locator('.compose-box textarea')).toBeVisible();
    });

    test('Scenario: SSE connection establishes', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await expect(page.locator('.compose-box textarea')).toBeEnabled();
    });

    test('Scenario: Timeline area renders', async ({ page }) => {
        await page.goto(BASE_URL);
        await expect(page.locator('#app')).toBeVisible();
    });
});
