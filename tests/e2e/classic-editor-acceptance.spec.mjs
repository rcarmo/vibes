// @ts-check
import { test, expect } from '@playwright/test';

async function start(page) {
  await page.goto('/');
  await page.locator('.app-shell').waitFor();
  const sidebar = page.locator('.workspace-sidebar');
  if (!(await sidebar.isVisible())) {
    await page.getByTestId('hamburger').click();
    await page.getByRole('menuitem', { name: 'Show workspace', exact: true }).click();
  }
}
async function open(page, name) {
  const label = page.locator('.workspace-row .workspace-label', { hasText: name }).first();
  await label.click();
  await page.locator('.workspace-edit').click();
  await expect(page.locator('.tab-item', { hasText: name }).first()).toBeVisible();
}

test('@ux-editor-001 switching files keeps the editor visible without a loading placeholder', async ({ page }) => {
  await start(page); await open(page, 'README.md'); await open(page, 'SPEC.md');
  await page.locator('.tab-item', { hasText: 'README.md' }).first().click();
  await expect(page.locator('.editor-pane')).toBeVisible();
  await expect(page.locator('.editor-pane')).not.toContainText(/loading/i);
});

test('@ux-editor-002 dismissing dirty-tab close confirmation keeps the tab open', async ({ page }) => {
  await start(page); await open(page, 'README.md');
  await page.locator('.cm-content').click(); await page.keyboard.type('dirty marker');
  await expect(page.locator('.tab-item.dirty')).toBeVisible();
  page.once('dialog', dialog => dialog.dismiss());
  await page.locator('.tab-item.dirty .tab-close').click();
  await expect(page.locator('.tab-item', { hasText: 'README.md' })).toBeVisible();
});

test.fixme('@ux-editor-003 primary mouse-down activates an inactive tab before mouse-up', async ({ page }) => {
  await start(page); await open(page, 'README.md'); await open(page, 'SPEC.md');
  const inactive = page.locator('.tab-item', { hasText: 'README.md' }).first();
  const box = await inactive.boundingBox(); if (!box) throw new Error('inactive tab has no box');
  await page.mouse.move(box.x + 10, box.y + 10); await page.mouse.down();
  await expect(inactive).toHaveClass(/active/);
  await expect(page.locator('.editor-pane')).toContainText('README');
  await page.mouse.up();
});

test('@ux-editor-004 markdown preview remains rendered and persists height after resize', async ({ page }) => {
  await start(page); await open(page, 'README.md');
  const tab = page.locator('.tab-item', { hasText: 'README.md' }).first();
  await tab.click({ button: 'right' });
  await page.locator('.tab-context-menu button', { hasText: 'Preview' }).click();
  const panel = page.locator('.md-preview-panel');
  await expect(panel).toBeVisible(); await expect(panel.locator('.md-preview-body')).not.toBeEmpty();
  const before = await panel.boundingBox(); const splitter = page.locator('.md-preview-splitter'); const box = await splitter.boundingBox();
  if (!before || !box) throw new Error('preview geometry unavailable');
  await page.mouse.move(box.x + 10, box.y + 2); await page.mouse.down(); await page.mouse.move(box.x + 10, box.y - 40); await page.mouse.up();
  await expect(panel).toBeVisible(); await expect(panel.locator('.md-preview-body')).not.toBeEmpty();
  const after = await panel.boundingBox(); expect(after?.height).toBeGreaterThan(before.height + 20);
  await expect.poll(() => page.evaluate(() => Number(localStorage.getItem('vibes_md_preview_height')))).toBeGreaterThan(before.height + 20);
});
