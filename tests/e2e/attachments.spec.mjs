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

test('failed send retains attachments and retry reuses completed upload', async ({ page }) => {
    let uploads = 0;
    let sends = 0;
    let payload;
    await page.route('**/media/upload', async route => {
        uploads++;
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ id: 123 }) });
    });
    await page.route('**/agent/default/message', async route => {
        sends++;
        payload = route.request().postDataJSON();
        await route.fulfill({ status: sends === 1 ? 503 : 200, contentType: 'application/json', body: JSON.stringify(sends === 1 ? { error: 'Temporary send failure' } : { status: 'queued' }) });
    });
    await page.goto('/');
    await page.locator('input[type=file][hidden]').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('reference text') });
    await page.getByTitle('Send (Ctrl+Enter)', { exact: true }).click();
    await expect(page.locator('.compose-file-pill', { hasText: 'notes.txt' })).toBeVisible();
    await expect(page.getByText('Temporary send failure', { exact: true })).toBeVisible();
    await page.getByTitle('Send (Ctrl+Enter)', { exact: true }).click();
    await expect(page.locator('.compose-file-pill', { hasText: 'notes.txt' })).toHaveCount(0);
    expect(uploads).toBe(1);
    expect(sends).toBe(2);
    expect(payload.media_ids).toEqual([123]);
    expect(payload.content).toContain('Attachments:\n- attachment:123 (notes.txt)');
});

test('upload cancellation keeps draft and prevents send', async ({ page }) => {
    let sends = 0;
    await page.route('**/media/upload', async route => {
        await new Promise(resolve => setTimeout(resolve, 1500));
        await route.fulfill({ status: 201, contentType: 'application/json', body: '{"id":321}' }).catch(() => {});
    });
    await page.route('**/agent/default/message', async route => { sends++; await route.fulfill({ body: '{}' }); });
    await page.goto('/');
    await page.locator('input[type=file][hidden]').setInputFiles({ name: 'slow.txt', mimeType: 'text/plain', buffer: Buffer.from('data') });
    await page.getByTitle('Send (Ctrl+Enter)', { exact: true }).click();
    await expect(page.getByTestId('compose-upload-status')).toBeVisible();
    await expect(page.getByRole('progressbar')).toBeVisible();
    await page.getByRole('button', { name: 'Cancel upload' }).click();
    await expect(page.getByTestId('compose-upload-status')).toHaveCount(0);
    await expect(page.getByRole('alert')).toContainText('Upload cancelled');
    await expect(page.locator('.compose-file-pill', { hasText: 'slow.txt' })).toBeVisible();
    expect(sends).toBe(0);
});
