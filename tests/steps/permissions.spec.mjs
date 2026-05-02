import { test, expect } from '@playwright/test';
import { BASE_URL } from './helpers.mjs';

test.describe('Feature: Permission and Whitelist Management', () => {
    test('Scenario: List whitelist patterns (empty)', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/agent/whitelist`);
        expect(resp.ok()).toBeTruthy();
        expect(await resp.json()).toHaveProperty('patterns');
    });

    test('Scenario: Add a whitelist pattern', async ({ request }) => {
        const resp = await request.post(`${BASE_URL}/agent/whitelist`, {
            data: { pattern: 'BDD Add Test', description: 'test' },
        });
        expect(resp.status()).toBeLessThan(300);
        const list = await (await request.get(`${BASE_URL}/agent/whitelist`)).json();
        expect(list.patterns).toContain('BDD Add Test');
        // Cleanup
        await request.delete(`${BASE_URL}/agent/whitelist`, { data: { pattern: 'BDD Add Test' } });
    });

    test('Scenario: Remove a whitelist pattern', async ({ request }) => {
        await request.post(`${BASE_URL}/agent/whitelist`, {
            data: { pattern: 'BDD Remove Test', description: 'test' },
        });
        const resp = await request.delete(`${BASE_URL}/agent/whitelist`, {
            data: { pattern: 'BDD Remove Test' },
        });
        expect(resp.status()).toBe(204);
        const list = await (await request.get(`${BASE_URL}/agent/whitelist`)).json();
        expect(list.patterns).not.toContain('BDD Remove Test');
    });

    test('Scenario: Glob matching works', async ({ request }) => {
        await request.post(`${BASE_URL}/agent/whitelist`, {
            data: { pattern: 'Run *', description: 'glob test' },
        });
        const list = await (await request.get(`${BASE_URL}/agent/whitelist`)).json();
        expect(list.patterns).toContain('Run *');
        // Cleanup
        await request.delete(`${BASE_URL}/agent/whitelist`, { data: { pattern: 'Run *' } });
    });
});
