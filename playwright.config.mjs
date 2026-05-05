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
 * Screenshots are captured on every test (pass or fail) and stored under
 * test-results/ for evidence. The CI workflow converts the HTML report
 * to PDF for easy reading.
 */
export default defineConfig({
  testDir: './tests',
  testMatch: ['steps/*.spec.mjs'],
  timeout: 120_000,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  outputDir: 'test-results',
  use: {
    baseURL: process.env.VIBES_TEST_URL || 'http://127.0.0.1:8765',
    headless: true,
    // Capture screenshots on every test for evidence
    screenshot: 'on',
    // Full trace on failure for debugging
    trace: 'retain-on-failure',
    // Record video on failure
    video: 'retain-on-failure',
    viewport: { width: 1280, height: 800 },
  },
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
  ],
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
