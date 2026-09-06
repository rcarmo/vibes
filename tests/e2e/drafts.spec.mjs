import { test, expect } from '@playwright/test';

test('draft text and references restore on reload and clear after send', async ({ page }) => {
    await page.addInitScript(() => {
        if (!localStorage.getItem('draft-test-seeded')) {
            localStorage.setItem('vibes_compose_draft:default', JSON.stringify({ text: 'unsent draft', fileRefs: ['README.md'], folderRefs: ['src'], messageRefs: ['42'] }));
            localStorage.setItem('draft-test-seeded', '1');
        }
    });
    await page.goto('/');
    const input = page.locator('.compose-input-main textarea');
    await expect(input).toHaveValue('unsent draft');
    await expect(page.locator('.compose-file-pill')).toHaveCount(3);
    await input.fill('updated draft');
    await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('vibes_compose_draft:default')).text)).toBe('updated draft');
    await page.reload();
    await expect(input).toHaveValue('updated draft');
    await page.route('**/agent/default/message', route => route.fulfill({ contentType: 'application/json', body: '{"status":"queued"}' }));
    await input.press('Enter');
    await expect(input).toHaveValue('');
    await expect(page.locator('.compose-file-pill')).toHaveCount(0);
    await page.reload();
    await expect(input).toHaveValue('');
});
