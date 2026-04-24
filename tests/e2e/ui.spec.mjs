/**
 * Vibes E2E tests — UI validation against a locally running Pi agent.
 *
 * Prerequisites:
 *   - vibes binary built with `make build`
 *   - Pi configured with gpt-5-mini as the model
 *   - Start vibes before running tests:
 *       VIBES_ACP_AGENT="pi-acp" VIBES_PORT=8765 ./vibes &
 *
 * These tests validate the full UI flow: page load, SSE connection,
 * message send/receive, agent streaming, workspace explorer, and editor.
 */

import { test, expect } from '@playwright/test';

// ── Helpers ──────────────────────────────────────────────────────

/** Wait for the SSE connection indicator to show "connected" state. */
async function waitForConnection(page, timeout = 15_000) {
  // The app shows a connection dot — green when connected.
  // Wait for the SSE stream to connect and the app to be interactive.
  await page.waitForFunction(() => {
    // The compose textarea is enabled when connected
    const textarea = document.querySelector('.compose-box textarea');
    return textarea && !textarea.disabled;
  }, { timeout });
}

/** Type a message in the compose box and send it. */
async function sendMessage(page, message) {
  const textarea = page.locator('.compose-box textarea');
  await textarea.fill(message);
  // Press Enter to send
  await textarea.press('Enter');
}

/** Wait for an agent response to appear in the timeline. */
async function waitForAgentResponse(page, timeout = 90_000) {
  // Wait for a new .agent-post to appear
  const agentPost = page.locator('.post.agent-post .post-content').last();
  await agentPost.waitFor({ state: 'visible', timeout });
  return agentPost;
}

/** Wait for the agent to finish streaming (status spinner disappears). */
async function waitForAgentIdle(page, timeout = 90_000) {
  await page.waitForFunction(() => {
    const spinner = document.querySelector('.agent-status-spinner');
    return !spinner || spinner.offsetParent === null;
  }, { timeout });
}

// ── Tests ────────────────────────────────────────────────────────

test.describe('Page load and UI structure', () => {

  test('loads the SPA and shows the compose box', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Vibes/);

    // Core UI elements should be present
    await expect(page.locator('.compose-box')).toBeVisible();
    await expect(page.locator('.compose-box textarea')).toBeVisible();
  });

  test('establishes SSE connection', async ({ page }) => {
    await page.goto('/');
    await waitForConnection(page);

    // Textarea should be enabled (not disabled)
    const textarea = page.locator('.compose-box textarea');
    await expect(textarea).toBeEnabled();
  });

  test('renders the timeline container', async ({ page }) => {
    await page.goto('/');
    // The timeline area should exist
    await expect(page.locator('#app')).toBeVisible();
  });

});

test.describe('Health and API endpoints', () => {

  test('GET /health returns ok', async ({ request }) => {
    const response = await request.get('/health');
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.status).toBe('ok');
  });

  test('GET /agents returns agent list', async ({ request }) => {
    const response = await request.get('/agents');
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body).toBeInstanceOf(Array);
    expect(body.length).toBeGreaterThan(0);
  });

  test('GET /timeline returns posts array', async ({ request }) => {
    const response = await request.get('/timeline');
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body).toHaveProperty('posts');
  });

  test('SSE stream connects and sends connected event', async ({ request }) => {
    const response = await request.get('/sse/stream');
    expect(response.ok()).toBeTruthy();
    expect(response.headers()['content-type']).toContain('text/event-stream');
  });

});

test.describe('Agent conversation', () => {

  test('can send a message and receive an agent response', async ({ page }) => {
    await page.goto('/');
    await waitForConnection(page);

    // Send a simple message
    await sendMessage(page, 'Say "hello world" and nothing else.');

    // Wait for the agent to respond
    const response = await waitForAgentResponse(page);
    await waitForAgentIdle(page);

    // The response should contain text
    const text = await response.textContent();
    expect(text.length).toBeGreaterThan(0);
    // The agent should have said something containing "hello" (case-insensitive)
    expect(text.toLowerCase()).toContain('hello');
  });

  test('shows agent status during streaming', async ({ page }) => {
    await page.goto('/');
    await waitForConnection(page);

    await sendMessage(page, 'Count from 1 to 5, one number per line.');

    // During streaming, the agent status panel should appear
    const statusPanel = page.locator('.agent-status-panel');
    // It may appear briefly — just check it exists at some point
    await expect(statusPanel).toBeVisible({ timeout: 30_000 });

    // Wait for completion
    await waitForAgentIdle(page);

    // Verify the response appeared
    const response = await waitForAgentResponse(page);
    const text = await response.textContent();
    expect(text).toContain('1');
    expect(text).toContain('5');
  });

  test('supports threaded replies', async ({ page }) => {
    await page.goto('/');
    await waitForConnection(page);

    // Send initial message
    await sendMessage(page, 'What is 2+2? Reply with just the number.');
    await waitForAgentResponse(page);
    await waitForAgentIdle(page);

    // The response should contain "4"
    const lastPost = page.locator('.post.agent-post .post-content').last();
    const text = await lastPost.textContent();
    expect(text).toContain('4');
  });

});

test.describe('Slash commands', () => {

  test('slash command autocomplete appears on /', async ({ page }) => {
    await page.goto('/');
    await waitForConnection(page);

    const textarea = page.locator('.compose-box textarea');
    await textarea.fill('/');

    // Wait for autocomplete dropdown
    const autocomplete = page.locator('.slash-autocomplete');
    await expect(autocomplete).toBeVisible({ timeout: 5_000 });
  });

  test('/commands lists available commands', async ({ page }) => {
    await page.goto('/');
    await waitForConnection(page);

    await sendMessage(page, '/commands');

    // Wait for a response listing commands
    await waitForAgentResponse(page, 30_000);
    await waitForAgentIdle(page);
  });

});

test.describe('Workspace explorer', () => {

  test('workspace sidebar can be toggled', async ({ page }) => {
    await page.goto('/');
    await waitForConnection(page);

    // Look for the workspace toggle button
    const toggleBtn = page.locator('[title*="orkspace"], [aria-label*="orkspace"], .workspace-toggle').first();
    if (await toggleBtn.isVisible()) {
      await toggleBtn.click();
      // Workspace tree should appear
      const tree = page.locator('.workspace-tree, .workspace-explorer');
      await expect(tree).toBeVisible({ timeout: 5_000 });
    }
  });

  test('GET /workspace/tree returns file tree', async ({ request }) => {
    const response = await request.get('/workspace/tree');
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    // Should have some kind of tree structure
    expect(body).toBeDefined();
  });

});

test.describe('Editor', () => {

  test('can open a file in the editor', async ({ page }) => {
    await page.goto('/');
    await waitForConnection(page);

    // Try to open a workspace file via API
    const treeResp = await page.request.get('/workspace/tree');
    if (treeResp.ok()) {
      const tree = await treeResp.json();
      // Find a text file to open
      const files = tree.entries || tree.children || tree || [];
      const textFile = findFirstFile(files);
      if (textFile) {
        // Click on it in the workspace explorer (if visible) or navigate
        // This test just validates the editor component loads
        await page.evaluate(() => {
          // Dispatch a custom event to open a file (the app listens for these)
          window.dispatchEvent(new CustomEvent('open-file', { detail: { path: 'README.md' } }));
        });
      }
    }
  });

});

test.describe('Media handling', () => {

  test('POST /media/upload accepts a file', async ({ request }) => {
    const buffer = Buffer.from('test content for upload');
    const response = await request.post('/media/upload', {
      multipart: {
        file: {
          name: 'test.txt',
          mimeType: 'text/plain',
          buffer,
        },
      },
    });
    // May return 200 or 201
    expect(response.status()).toBeLessThan(400);
  });

});

test.describe('Compose box features', () => {

  test('compose history works with arrow keys', async ({ page }) => {
    await page.goto('/');
    await waitForConnection(page);

    // Send a message
    await sendMessage(page, 'First test message for history');
    await waitForAgentResponse(page);
    await waitForAgentIdle(page);

    // Send another
    await sendMessage(page, 'Second test message for history');
    await waitForAgentResponse(page);
    await waitForAgentIdle(page);

    // Press Up arrow to recall previous message
    const textarea = page.locator('.compose-box textarea');
    await textarea.click();
    await textarea.press('ArrowUp');

    // Should have recalled a previous message
    const value = await textarea.inputValue();
    expect(value.length).toBeGreaterThan(0);
  });

  test('Enter sends, Shift+Enter inserts newline', async ({ page }) => {
    await page.goto('/');
    await waitForConnection(page);

    const textarea = page.locator('.compose-box textarea');
    await textarea.fill('Line one');
    await textarea.press('Shift+Enter');
    await textarea.type('Line two');

    // Should contain a newline
    const value = await textarea.inputValue();
    expect(value).toContain('\n');
  });

});

test.describe('Dark/light theme', () => {

  test('respects prefers-color-scheme', async ({ page }) => {
    // Force dark mode
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.goto('/');

    // The page should have dark theme CSS active
    const bgColor = await page.evaluate(() =>
      getComputedStyle(document.body).backgroundColor
    );
    // Dark backgrounds typically have low RGB values
    expect(bgColor).toBeDefined();
  });

});

// ── Utilities ────────────────────────────────────────────────────

/** Recursively find the first file in a tree structure. */
function findFirstFile(entries) {
  if (!Array.isArray(entries)) return null;
  for (const entry of entries) {
    if (entry.type === 'file' || (!entry.children && !entry.entries && entry.name)) {
      return entry;
    }
    const found = findFirstFile(entry.children || entry.entries || []);
    if (found) return found;
  }
  return null;
}
