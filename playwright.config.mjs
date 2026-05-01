// @ts-check
import { defineConfig } from '@playwright/test';

/**
 * Playwright config for Vibes BDD/UX test pipeline.
 *
 * Tests are organized as:
 *   tests/features/*.feature  — Gherkin user stories (documentation)
 *   tests/steps/*.spec.mjs    — Playwright implementations of each scenario
 *   tests/e2e/*.spec.mjs      — Additional E2E tests (legacy)
 *
 * Usage:
 *   VIBES_ACP_AGENT="pi-acp" VIBES_PORT=8765 ./vibes &
 *   bunx playwright test
 *
 * Or via Makefile:
 *   make e2e
 */
export default defineConfig({
  testDir: './tests',
  testMatch: ['steps/*.spec.mjs', 'e2e/*.spec.mjs'],
  timeout: 120_000,
  retries: 0,
  workers: 1,
  use: {
    baseURL: process.env.VIBES_TEST_URL || 'http://127.0.0.1:8765',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
