// @ts-check
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: 0,
  // Each run owns its server/database; no stale manually launched process.
  webServer: {
    command: 'PYTHONPATH=src VIBES_HOST=127.0.0.1 VIBES_PORT=8765 VIBES_DB_PATH=:memory: VIBES_ACP_AGENT=/nonexistent-e2e-agent VIBES_PI_ENABLED=false .venv/bin/python -m vibes.app',
    url: 'http://127.0.0.1:8765/health',
    reuseExistingServer: false,
    timeout: 15000,
  },
  use: {
    baseURL: 'http://127.0.0.1:8765',
    headless: true,
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
});
