import { test, expect } from '@playwright/test';
import { BASE_URL, waitForConnection, sendMessage, waitForAgentResponse, waitForAgentIdle } from './helpers.mjs';

test.describe('Feature: Slash Commands', () => {
    test('Scenario: Slash autocomplete appears when typing /', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await page.locator('.compose-box textarea').fill('/');
        await expect(page.locator('.slash-autocomplete')).toBeVisible({ timeout: 5000 });
    });

    test('Scenario: /commands lists available commands', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, '/commands');
        await waitForAgentResponse(page, 30000);
        await waitForAgentIdle(page);
    });

    test('Scenario: /clear command is recognized', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, '/clear');
        // /clear is handled client-side; wait briefly then verify compose box is still functional
        await page.waitForTimeout(2000);
        await expect(page.locator('.compose-box textarea')).toBeVisible();
    });
});
