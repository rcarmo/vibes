import { test, expect } from '@playwright/test';
import { BASE_URL } from './helpers.mjs';

test.describe('Feature: Timeline and Posts', () => {
    test('Scenario: Create a new post', async ({ request }) => {
        const resp = await request.post(`${BASE_URL}/post`, {
            data: { content: 'Hello from BDD' },
        });
        expect(resp.status()).toBe(201);
        expect(await resp.json()).toHaveProperty('id');
    });

    test('Scenario: Timeline shows created posts', async ({ request }) => {
        await request.post(`${BASE_URL}/post`, { data: { content: 'Timeline test post' } });
        const resp = await request.get(`${BASE_URL}/timeline`);
        const body = await resp.json();
        expect(body.posts.length).toBeGreaterThan(0);
    });

    test('Scenario: Delete a post', async ({ request }) => {
        const create = await request.post(`${BASE_URL}/post`, { data: { content: 'Delete me' } });
        const { id } = await create.json();
        const resp = await request.delete(`${BASE_URL}/post/${id}`);
        expect(resp.status()).toBe(204);
    });

    test('Scenario: Reply to a thread', async ({ request }) => {
        const parent = await request.post(`${BASE_URL}/post`, { data: { content: 'Parent post' } });
        const { id: threadId } = await parent.json();
        const resp = await request.post(`${BASE_URL}/thread`, {
            data: { thread_id: threadId, content: 'Reply post' },
        });
        expect(resp.status()).toBe(201);
    });

    test('Scenario: Get a thread', async ({ request }) => {
        const parent = await request.post(`${BASE_URL}/post`, { data: { content: 'Thread parent' } });
        const { id: threadId } = await parent.json();
        await request.post(`${BASE_URL}/thread`, { data: { thread_id: threadId, content: 'Thread reply' } });
        const resp = await request.get(`${BASE_URL}/thread/${threadId}`);
        const body = await resp.json();
        expect(body.posts.length).toBe(2);
    });

    test('Scenario: Search posts', async ({ request }) => {
        await request.post(`${BASE_URL}/post`, { data: { content: 'unique searchable keyword zxcvbn' } });
        const resp = await request.get(`${BASE_URL}/search?q=zxcvbn`);
        const body = await resp.json();
        expect(body.posts.length).toBeGreaterThan(0);
    });
});
