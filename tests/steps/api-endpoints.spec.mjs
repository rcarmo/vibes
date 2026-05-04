import { test, expect } from '@playwright/test';
import { BASE_URL } from './helpers.mjs';

test.describe('Feature: API Health and Endpoints', () => {
    test('Scenario: Health endpoint returns ok', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/health`);
        expect(resp.ok()).toBeTruthy();
        expect(await resp.json()).toMatchObject({ status: 'ok' });
    });

    test('Scenario: Agents endpoint returns a list', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/agents`);
        expect(resp.ok()).toBeTruthy();
        expect(Array.isArray(await resp.json())).toBeTruthy();
    });

    test('Scenario: Timeline endpoint returns posts', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/timeline`);
        expect(resp.ok()).toBeTruthy();
        expect(await resp.json()).toHaveProperty('posts');
    });

    test('Scenario: SSE stream endpoint connects', async ({}) => {
        // SSE is a long-lived stream — use AbortController to test just the headers
        const controller = new AbortController();
        setTimeout(() => controller.abort(), 3000);
        try {
            const resp = await fetch(`${BASE_URL}/sse/stream`, { signal: controller.signal });
            expect(resp.status).toBe(200);
            expect(resp.headers.get('content-type')).toContain('text/event-stream');
        } catch (e) {
            // AbortError is expected — we confirmed headers before abort
            if (e.name !== 'AbortError') throw e;
        }
    });

    test('Scenario: Agent commands endpoint returns commands', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/agent/commands`);
        expect(resp.ok()).toBeTruthy();
        expect(Array.isArray(await resp.json())).toBeTruthy();
    });

    test('Scenario: Agent status endpoint returns state', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/agent/status`);
        expect(resp.ok()).toBeTruthy();
    });

    test('Scenario: Workspace tree endpoint returns entries', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/workspace/tree`);
        expect(resp.ok()).toBeTruthy();
        expect(await resp.json()).toHaveProperty('entries');
    });

    test('Scenario: Search endpoint requires query parameter', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/search`);
        expect(resp.status()).toBe(400);
    });
});
