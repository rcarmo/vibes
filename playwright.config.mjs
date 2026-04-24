// @ts-check
import { defineConfig } from '@playwright/test';

/*
 * Playwright E2E tests for Vibes.
 *
 * These tests run against a locally-running vibes instance backed by Pi
 * (via pi-acp or native RPC). The instance must be started before running:
 *
 *   VIBES_ACP_AGENT="pi-acp" VIBES_PORT=8765 ./vibes &
 *   bunx playwright test
 *
 * Or use `make e2e` which handles setup/teardown.
 */
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000,     // 2 min per test — agents can be slow
  retries: 0,
  workers: 1,           // serial — one agent session at a time
  use: {
    baseURL: 'http://127.0.0.1:8765',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
