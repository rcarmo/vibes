import { test, expect } from '@playwright/test';
import { BASE_URL } from './helpers.mjs';

test.describe('Feature: Link Preview', () => {
    test('Scenario: Fetch a link preview', async ({ request }) => {
        const resp = await request.post(`${BASE_URL}/link-preview`, {
            data: { url: 'https://example.com' },
        });
        expect(resp.ok()).toBeTruthy();
        const body = await resp.json();
        expect(body).toHaveProperty('url');
        expect(body).toHaveProperty('title');
    });
});
