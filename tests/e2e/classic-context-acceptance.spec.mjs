// @ts-check
import { test, expect } from '@playwright/test';

async function contextFixture(page, usage) {
  await page.route('**/sessions/*/model-state', route => route.fulfill({ json: { available: true, model: { provider: 'test', id: 'model' } } }));
  await page.route('**/agent/context?*', route => route.fulfill({ json: usage }));
  await page.goto('/');
}

test('@ux-context-001 supplied usage is formatted, accessible, and fill is clamped', async ({ page }) => {
  await contextFixture(page, { percent: 125.4, tokens: 12345, contextWindow: 20000 });
  const pie = page.locator('.compose-context-pie');
  await expect(pie).toHaveAttribute('title', /Context: 12K \/ 20K tokens \(125%\)/);
  await expect(pie).toHaveAttribute('aria-label', /Context: 12K \/ 20K tokens \(125%\)/);
  const dash = await pie.locator('circle').nth(1).getAttribute('stroke-dasharray');
  const [filled, circumference] = String(dash).split(' ').map(Number);
  expect(filled).toBeCloseTo(circumference, 5);
});

test('@ux-context-002 missing token count is not fabricated', async ({ page }) => {
  await contextFixture(page, { percent: 41.2, tokens: null, contextWindow: 20000 });
  const pie = page.locator('.compose-context-pie');
  await expect(pie).toHaveAttribute('aria-label', /^Context: 41%/);
  await expect(pie).not.toHaveAttribute('aria-label', /20K tokens/);
});

for (const [percent, token] of [[91, '--context-red'], [90, '--context-amber'], [75, '--context-green']]) {
  test(`@ux-context-005 ${percent}% uses ${token}`, async ({ page }) => {
    await contextFixture(page, { percent, tokens: 100, contextWindow: 1000 });
    await expect(page.locator('.compose-context-pie circle').nth(1)).toHaveAttribute('stroke', new RegExp(token));
  });
}
