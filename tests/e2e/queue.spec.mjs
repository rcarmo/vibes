import { test, expect } from '@playwright/test';

test('queue move buttons submit direction and reflect server order', async ({ page }) => {
    let items = [{ row_id: -1, content: 'first queued', agent_id: 'default', thread_id: 1 }, { row_id: -2, content: 'second queued', agent_id: 'default', thread_id: 1 }];
    let payload;
    await page.route('**/agent/queue?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items, pending_steers: [] }) }));
    await page.route('**/agent/queue-reorder', async route => {
        payload = route.request().postDataJSON();
        items = [items[1], items[0]];
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items }) });
    });
    await page.goto('/');
    const rows = page.locator('.compose-queue-item');
    await expect(rows).toHaveCount(2);
    await expect(rows.first().getByRole('button', { name: 'Move up in queue' })).toBeDisabled();
    await rows.nth(1).getByRole('button', { name: 'Move up in queue' }).click();
    await expect(rows.first()).toContainText('second queued');
    expect(payload).toEqual({ row_id: -2, direction: 'up' });
});

test('queued reference blocks render as pills without hiding invalid lines', async ({ page }) => {
    const content = 'Review this\n\nFiles:\n- src/main.py\n\nMessages:\n- 42\n- invalid-ref\n\nAttachments:\n- attachment:7 (notes.txt)';
    await page.route('**/agent/queue?*', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [{ row_id: -1, content, agent_id: 'default', thread_id: 1 }] }) }));
    await page.goto('/');
    const row = page.locator('.compose-queue-item');
    await expect(row.locator('.compose-file-pill')).toHaveCount(3);
    await expect(row.locator('.compose-file-pill', { hasText: 'main.py' })).toBeVisible();
    await expect(row.locator('.compose-file-pill', { hasText: 'msg:42' })).toBeVisible();
    await expect(row.locator('.compose-file-pill', { hasText: 'notes.txt' })).toBeVisible();
    await expect(row.locator('.compose-queue-text')).toContainText('invalid-ref');
});
