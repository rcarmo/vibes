import { test, expect } from '@playwright/test';

test('queue move buttons submit direction and reflect server order', async ({ page }) => {
    let items = [{ row_id: -1, content: 'first queued', agent_id: 'default', thread_id: 1 }, { row_id: -2, content: 'second queued', agent_id: 'default', thread_id: 1 }];
    let payload;
    await page.route('**/agents/status', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ queued_followups: items }) }));
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
