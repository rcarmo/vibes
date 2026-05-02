import { test, expect } from '@playwright/test';
import { BASE_URL } from './helpers.mjs';

test.describe('Feature: Media Upload and Serving', () => {
    test('Scenario: Upload a text file', async ({ request }) => {
        const resp = await request.post(`${BASE_URL}/media/upload`, {
            multipart: { file: { name: 'bdd-upload.txt', mimeType: 'text/plain', buffer: Buffer.from('upload test') } },
        });
        expect(resp.status()).toBeLessThan(300);
        const body = await resp.json();
        expect(body).toHaveProperty('id');
        expect(body).toHaveProperty('url');
    });

    test('Scenario: Serve an uploaded file', async ({ request }) => {
        const upload = await request.post(`${BASE_URL}/media/upload`, {
            multipart: { file: { name: 'bdd-serve.txt', mimeType: 'text/plain', buffer: Buffer.from('serve me') } },
        });
        const { url } = await upload.json();
        const resp = await request.get(`${BASE_URL}${url}`);
        expect(resp.ok()).toBeTruthy();
        expect((await resp.body()).toString()).toBe('serve me');
    });

    test('Scenario: Media info endpoint', async ({ request }) => {
        const upload = await request.post(`${BASE_URL}/media/upload`, {
            multipart: { file: { name: 'bdd-info.txt', mimeType: 'text/plain', buffer: Buffer.from('info test') } },
        });
        const { id } = await upload.json();
        const resp = await request.get(`${BASE_URL}/media/${id}/info`);
        expect(resp.ok()).toBeTruthy();
        expect(await resp.json()).toHaveProperty('filename');
    });
});
