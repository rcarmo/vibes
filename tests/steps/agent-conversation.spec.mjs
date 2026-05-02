import { test, expect } from '@playwright/test';
import { BASE_URL, waitForConnection, sendMessage, waitForAgentResponse, waitForAgentIdle } from './helpers.mjs';

test.describe('Feature: Agent Conversation', () => {
    test('Scenario: Send a message and receive a response', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, 'Say hello world and nothing else.');
        const response = await waitForAgentResponse(page);
        await waitForAgentIdle(page);
        expect((await response.textContent()).toLowerCase()).toContain('hello');
    });

    test('Scenario: Agent shows status during streaming', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, 'Count from 1 to 5, one number per line.');
        await expect(page.locator('.agent-status-panel')).toBeVisible({ timeout: 30000 });
        await waitForAgentIdle(page);
        const response = await waitForAgentResponse(page);
        const text = await response.textContent();
        expect(text).toContain('1');
        expect(text).toContain('5');
    });

    test('Scenario: Agent handles simple math', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, 'What is 2+2? Reply with just the number.');
        await waitForAgentIdle(page);
        const response = await waitForAgentResponse(page);
        expect(await response.textContent()).toContain('4');
    });
});
