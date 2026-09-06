import { test, expect } from '@playwright/test';

test('composer accepts nonimage files from picker and clipboard', async ({ page }) => {
    await page.goto('/');
    await page.locator('input[type=file][hidden]').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('reference text') });
    await expect(page.locator('.compose-file-pill', { hasText: 'notes.txt' })).toBeVisible();
    await page.locator('.compose-input-main textarea').evaluate(element => {
        const transfer = new DataTransfer();
        transfer.items.add(new File(['csv'], 'data.csv', { type: 'text/csv' }));
        element.dispatchEvent(new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }));
    });
    await expect(page.locator('.compose-file-pill', { hasText: 'data.csv' })).toBeVisible();
    await page.locator('.compose-file-pill', { hasText: 'notes.txt' }).getByTitle('Remove attachment').click();
    await expect(page.locator('.compose-file-pill', { hasText: 'notes.txt' })).toHaveCount(0);
});
