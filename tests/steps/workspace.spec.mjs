import { test, expect } from '@playwright/test';
import { BASE_URL } from './helpers.mjs';

test.describe('Feature: Workspace Explorer', () => {
    test('Scenario: Workspace tree loads files', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/workspace/tree`);
        expect(resp.ok()).toBeTruthy();
        expect(await resp.json()).toHaveProperty('entries');
    });

    test('Scenario: Read a workspace file', async ({ request }) => {
        // Create first
        await request.post(`${BASE_URL}/workspace/create`, {
            data: { path: '', name: 'bdd-read.txt', content: 'hello world' },
        });
        const resp = await request.get(`${BASE_URL}/workspace/file?path=bdd-read.txt`);
        expect(resp.ok()).toBeTruthy();
        const body = await resp.json();
        expect(body.content).toBe('hello world');
        await request.delete(`${BASE_URL}/workspace/file?path=bdd-read.txt`);
    });

    test('Scenario: Create a new file', async ({ request }) => {
        const resp = await request.post(`${BASE_URL}/workspace/create`, {
            data: { path: '', name: 'bdd-create.txt', content: 'created by test' },
        });
        expect(resp.status()).toBeLessThan(300);
        // Verify
        const read = await request.get(`${BASE_URL}/workspace/file?path=bdd-create.txt`);
        expect(read.ok()).toBeTruthy();
        await request.delete(`${BASE_URL}/workspace/file?path=bdd-create.txt`);
    });

    test('Scenario: Update a file', async ({ request }) => {
        await request.post(`${BASE_URL}/workspace/create`, {
            data: { path: '', name: 'bdd-update.txt', content: 'original' },
        });
        const resp = await request.put(`${BASE_URL}/workspace/file`, {
            data: { path: 'bdd-update.txt', content: 'updated' },
        });
        expect(resp.ok()).toBeTruthy();
        const read = await request.get(`${BASE_URL}/workspace/file?path=bdd-update.txt`);
        expect((await read.json()).content).toBe('updated');
        await request.delete(`${BASE_URL}/workspace/file?path=bdd-update.txt`);
    });

    test('Scenario: Delete a file', async ({ request }) => {
        await request.post(`${BASE_URL}/workspace/create`, {
            data: { path: '', name: 'bdd-delete.txt', content: 'delete me' },
        });
        const resp = await request.delete(`${BASE_URL}/workspace/file?path=bdd-delete.txt`);
        expect(resp.status()).toBe(204);
    });

    test('Scenario: Path traversal is rejected', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/workspace/file?path=../../etc/passwd`);
        expect(resp.status()).not.toBe(200);
    });
});
