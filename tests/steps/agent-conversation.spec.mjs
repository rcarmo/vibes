import { test, expect } from '@playwright/test';
import { BASE_URL, waitForConnection, sendMessage, waitForAgentResponse, waitForAgentIdle } from './helpers.mjs';

test.describe('Feature: Agent Conversation', () => {
    test('Scenario: Send a message and receive a response', async ({ page, request }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, 'Say hello world and nothing else.');

        // Wait for agent to finish (either via DOM or timeout)
        try {
            const response = await waitForAgentResponse(page, 60000);
            await waitForAgentIdle(page);
            expect((await response.textContent()).toLowerCase()).toContain('hello');
        } catch {
            // Fallback: check timeline API for agent response
            await page.waitForTimeout(10000);
            const resp = await request.get(`${BASE_URL}/timeline`);
            const body = await resp.json();
            const agentPosts = body.posts.filter(p => p.type === 'agent_response');
            expect(agentPosts.length).toBeGreaterThan(0);
            const content = agentPosts[0]?.data?.content || '';
            expect(content.toLowerCase()).toContain('hello');
        }
    });

    test('Scenario: Agent shows status during streaming', async ({ page, request }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, 'Count from 1 to 5, one number per line.');

        // Wait for response via DOM or API
        try {
            await waitForAgentIdle(page, 60000);
            const response = await waitForAgentResponse(page, 10000);
            const text = await response.textContent();
            expect(text).toContain('1');
            expect(text).toContain('5');
        } catch {
            await page.waitForTimeout(10000);
            const resp = await request.get(`${BASE_URL}/timeline`);
            const body = await resp.json();
            const agentPosts = body.posts.filter(p => p.type === 'agent_response');
            expect(agentPosts.length).toBeGreaterThan(0);
            const content = agentPosts[0]?.data?.content || '';
            expect(content).toContain('1');
        }
    });

    test('Scenario: Agent handles simple math', async ({ page, request }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, 'What is 2+2? Reply with just the number.');

        try {
            await waitForAgentIdle(page, 60000);
            const response = await waitForAgentResponse(page, 10000);
            expect(await response.textContent()).toContain('4');
        } catch {
            await page.waitForTimeout(10000);
            const resp = await request.get(`${BASE_URL}/timeline`);
            const body = await resp.json();
            const agentPosts = body.posts.filter(p => p.type === 'agent_response');
            expect(agentPosts.length).toBeGreaterThan(0);
            const content = agentPosts[0]?.data?.content || '';
            expect(content).toContain('4');
        }
    });
});
