import { test, expect } from '@playwright/test';
import { BASE_URL } from './helpers.mjs';

test.describe('Feature: Agent Switching', () => {
    test('Scenario: List available agents', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/agents`);
        const body = await resp.json();
        expect(Array.isArray(body)).toBeTruthy();
        if (body.length > 0) {
            expect(body[0]).toHaveProperty('id');
            expect(body[0]).toHaveProperty('status');
        }
    });

    test('Scenario: Get agent status', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/agent/status`);
        const body = await resp.json();
        expect(body).toHaveProperty('status');
        expect(body).toHaveProperty('agent_id');
    });

    test('Scenario: Get agent models', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/agent/models`);
        const body = await resp.json();
        expect(body).toHaveProperty('current');
        expect(body).toHaveProperty('models');
    });
});
