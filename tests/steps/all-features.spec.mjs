/**
 * Playwright BDD step definitions for Vibes Gherkin features.
 *
 * This file implements all Given/When/Then steps referenced in the .feature files.
 * Uses @playwright/test with a BDD-compatible wrapper.
 *
 * Run: bunx playwright test tests/steps/
 */

import { test, expect } from '@playwright/test';

// ── Helpers ──────────────────────────────────────────────────────

const BASE_URL = process.env.VIBES_TEST_URL || 'http://127.0.0.1:8765';

async function waitForConnection(page, timeout = 15000) {
    await page.waitForFunction(() => {
        const textarea = document.querySelector('.compose-box textarea');
        return textarea && !textarea.disabled;
    }, { timeout });
}

async function sendMessage(page, message) {
    const textarea = page.locator('.compose-box textarea');
    await textarea.fill(message);
    await textarea.press('Enter');
}

async function waitForAgentResponse(page, timeout = 90000) {
    const agentPost = page.locator('.post.agent-post .post-content').last();
    await agentPost.waitFor({ state: 'visible', timeout });
    return agentPost;
}

async function waitForAgentIdle(page, timeout = 90000) {
    await page.waitForFunction(() => {
        const spinner = document.querySelector('.agent-status-spinner');
        return !spinner || spinner.offsetParent === null;
    }, { timeout });
}

// ── Feature: Page Load and Connection ────────────────────────────

test.describe('Feature: Page Load and Connection', () => {
    test('Scenario: SPA loads with correct title', async ({ page }) => {
        await page.goto(BASE_URL);
        await expect(page).toHaveTitle(/Vibes/);
    });

    test('Scenario: Compose box is visible on load', async ({ page }) => {
        await page.goto(BASE_URL);
        await expect(page.locator('.compose-box')).toBeVisible();
        await expect(page.locator('.compose-box textarea')).toBeVisible();
    });

    test('Scenario: SSE connection establishes', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await expect(page.locator('.compose-box textarea')).toBeEnabled();
    });

    test('Scenario: Timeline area renders', async ({ page }) => {
        await page.goto(BASE_URL);
        await expect(page.locator('#app')).toBeVisible();
    });
});

// ── Feature: API Health and Endpoints ────────────────────────────

test.describe('Feature: API Health and Endpoints', () => {
    test('Scenario: Health endpoint returns ok', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/health`);
        expect(resp.ok()).toBeTruthy();
        expect(await resp.json()).toMatchObject({ status: 'ok' });
    });

    test('Scenario: Agents endpoint returns a list', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/agents`);
        expect(resp.ok()).toBeTruthy();
        const body = await resp.json();
        expect(Array.isArray(body)).toBeTruthy();
    });

    test('Scenario: Timeline endpoint returns posts', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/timeline`);
        expect(resp.ok()).toBeTruthy();
        const body = await resp.json();
        expect(body).toHaveProperty('posts');
    });

    test('Scenario: SSE stream endpoint connects', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/sse/stream`);
        expect(resp.ok()).toBeTruthy();
        expect(resp.headers()['content-type']).toContain('text/event-stream');
    });

    test('Scenario: Agent commands endpoint returns commands', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/agent/commands`);
        expect(resp.ok()).toBeTruthy();
        const body = await resp.json();
        expect(Array.isArray(body)).toBeTruthy();
    });

    test('Scenario: Agent status endpoint returns state', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/agent/status`);
        expect(resp.ok()).toBeTruthy();
    });

    test('Scenario: Workspace tree endpoint returns entries', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/workspace/tree`);
        expect(resp.ok()).toBeTruthy();
        const body = await resp.json();
        expect(body).toHaveProperty('entries');
    });

    test('Scenario: Search endpoint requires query parameter', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/search`);
        expect(resp.status()).toBe(400);
    });
});

// ── Feature: Agent Conversation ──────────────────────────────────

test.describe('Feature: Agent Conversation', () => {
    test('Scenario: Send a message and receive a response', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, 'Say hello world and nothing else.');
        const response = await waitForAgentResponse(page);
        await waitForAgentIdle(page);
        const text = await response.textContent();
        expect(text.toLowerCase()).toContain('hello');
    });

    test('Scenario: Agent shows status during streaming', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, 'Count from 1 to 5, one number per line.');
        const statusPanel = page.locator('.agent-status-panel');
        await expect(statusPanel).toBeVisible({ timeout: 30000 });
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
        const text = await response.textContent();
        expect(text).toContain('4');
    });
});

// ── Feature: Slash Commands ──────────────────────────────────────

test.describe('Feature: Slash Commands', () => {
    test('Scenario: Slash autocomplete appears when typing /', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        const textarea = page.locator('.compose-box textarea');
        await textarea.fill('/');
        await expect(page.locator('.slash-autocomplete')).toBeVisible({ timeout: 5000 });
    });

    test('Scenario: /commands lists available commands', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, '/commands');
        await waitForAgentResponse(page, 30000);
        await waitForAgentIdle(page);
    });
});

// ── Feature: Workspace Explorer ──────────────────────────────────

test.describe('Feature: Workspace Explorer', () => {
    test('Scenario: Workspace tree loads files', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/workspace/tree`);
        expect(resp.ok()).toBeTruthy();
        const body = await resp.json();
        expect(body).toHaveProperty('entries');
    });

    test('Scenario: Create and read a file', async ({ request }) => {
        // Create
        const createResp = await request.post(`${BASE_URL}/workspace/create`, {
            data: { path: '', name: 'bdd-test.txt', content: 'hello from bdd' },
        });
        expect(createResp.status()).toBeLessThan(300);

        // Read
        const readResp = await request.get(`${BASE_URL}/workspace/file?path=bdd-test.txt`);
        expect(readResp.ok()).toBeTruthy();
        const body = await readResp.json();
        expect(body.content).toBe('hello from bdd');

        // Clean up
        await request.delete(`${BASE_URL}/workspace/file?path=bdd-test.txt`);
    });

    test('Scenario: Update a file', async ({ request }) => {
        // Create
        await request.post(`${BASE_URL}/workspace/create`, {
            data: { path: '', name: 'bdd-update.txt', content: 'original' },
        });

        // Update
        const updateResp = await request.put(`${BASE_URL}/workspace/file`, {
            data: { path: 'bdd-update.txt', content: 'updated' },
        });
        expect(updateResp.ok()).toBeTruthy();

        // Verify
        const readResp = await request.get(`${BASE_URL}/workspace/file?path=bdd-update.txt`);
        const body = await readResp.json();
        expect(body.content).toBe('updated');

        // Clean up
        await request.delete(`${BASE_URL}/workspace/file?path=bdd-update.txt`);
    });

    test('Scenario: Path traversal is rejected', async ({ request }) => {
        const resp = await request.get(`${BASE_URL}/workspace/file?path=../../etc/passwd`);
        expect(resp.status()).not.toBe(200);
    });
});

// ── Feature: Media Upload and Serving ────────────────────────────

test.describe('Feature: Media Upload and Serving', () => {
    test('Scenario: Upload and serve a file', async ({ request }) => {
        const buffer = Buffer.from('test media content');
        const uploadResp = await request.post(`${BASE_URL}/media/upload`, {
            multipart: {
                file: { name: 'bdd-media.txt', mimeType: 'text/plain', buffer },
            },
        });
        expect(uploadResp.status()).toBeLessThan(300);
        const { id, url } = await uploadResp.json();
        expect(id).toBeGreaterThan(0);

        // Serve
        const serveResp = await request.get(`${BASE_URL}${url}`);
        expect(serveResp.ok()).toBeTruthy();
        expect((await serveResp.body()).toString()).toBe('test media content');
    });

    test('Scenario: Media info endpoint', async ({ request }) => {
        const buffer = Buffer.from('info test');
        const uploadResp = await request.post(`${BASE_URL}/media/upload`, {
            multipart: {
                file: { name: 'bdd-info.txt', mimeType: 'text/plain', buffer },
            },
        });
        const { id } = await uploadResp.json();

        const infoResp = await request.get(`${BASE_URL}/media/${id}/info`);
        expect(infoResp.ok()).toBeTruthy();
        const info = await infoResp.json();
        expect(info).toHaveProperty('filename');
    });
});

// ── Feature: Compose Box UX ─────────────────────────────────────

test.describe('Feature: Compose Box UX', () => {
    test('Scenario: Shift+Enter inserts newline', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        const textarea = page.locator('.compose-box textarea');
        await textarea.fill('Line one');
        await textarea.press('Shift+Enter');
        await textarea.type('Line two');
        const value = await textarea.inputValue();
        expect(value).toContain('\n');
    });

    test('Scenario: Compose history with arrow keys', async ({ page }) => {
        await page.goto(BASE_URL);
        await waitForConnection(page);
        await sendMessage(page, 'BDD history test message one');
        await waitForAgentResponse(page);
        await waitForAgentIdle(page);
        await sendMessage(page, 'BDD history test message two');
        await waitForAgentResponse(page);
        await waitForAgentIdle(page);

        const textarea = page.locator('.compose-box textarea');
        await textarea.click();
        await textarea.press('ArrowUp');
        const value = await textarea.inputValue();
        expect(value.length).toBeGreaterThan(0);
    });
});

// ── Feature: Theme Support ───────────────────────────────────────

test.describe('Feature: Theme Support', () => {
    test('Scenario: Dark mode renders', async ({ page }) => {
        await page.emulateMedia({ colorScheme: 'dark' });
        await page.goto(BASE_URL);
        const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
        expect(bg).toBeDefined();
    });

    test('Scenario: Light mode renders', async ({ page }) => {
        await page.emulateMedia({ colorScheme: 'light' });
        await page.goto(BASE_URL);
        const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
        expect(bg).toBeDefined();
    });
});

// ── Feature: Permission and Whitelist Management ─────────────────

test.describe('Feature: Permission and Whitelist Management', () => {
    test('Scenario: List, add, and remove whitelist patterns', async ({ request }) => {
        // List (should be empty or have previous items)
        const listResp = await request.get(`${BASE_URL}/agent/whitelist`);
        expect(listResp.ok()).toBeTruthy();
        const { patterns: initial } = await listResp.json();
        expect(Array.isArray(initial)).toBeTruthy();

        // Add
        const addResp = await request.post(`${BASE_URL}/agent/whitelist`, {
            data: { pattern: 'BDD Test *', description: 'BDD test pattern' },
        });
        expect(addResp.status()).toBeLessThan(300);

        // Verify added
        const afterAdd = await (await request.get(`${BASE_URL}/agent/whitelist`)).json();
        expect(afterAdd.patterns).toContain('BDD Test *');

        // Remove
        const removeResp = await request.delete(`${BASE_URL}/agent/whitelist`, {
            data: { pattern: 'BDD Test *' },
        });
        expect(removeResp.status()).toBe(204);

        // Verify removed
        const afterRemove = await (await request.get(`${BASE_URL}/agent/whitelist`)).json();
        expect(afterRemove.patterns).not.toContain('BDD Test *');
    });
});
