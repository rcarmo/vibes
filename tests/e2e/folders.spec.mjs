import { test, expect } from '@playwright/test';

test('folder selection creates removable reference and folder-only message', async ({ page }) => {
    let payload;
    await page.route('**/agent/default/message', async route => {
        payload = route.request().postDataJSON();
        await route.fulfill({ contentType: 'application/json', body: '{"status":"queued"}' });
    });
    await page.goto('/');
    if (!(await page.locator('.workspace-sidebar').isVisible())) await page.locator('.workspace-toggle-tab').click();
    await page.locator('.workspace-row[data-path="src"]').click();
    const pill = page.locator('.compose-file-pill[title="src"]');
    await expect(pill).toBeVisible();
    await expect(pill.getByTitle('Remove folder')).toBeVisible();
    await page.getByTitle('Send (Enter); steer with Ctrl/Cmd+Enter', { exact: true }).click();
    await expect.poll(() => payload?.content).toBe('Folders:\n- src');
    await expect(pill).toHaveCount(0);
});
