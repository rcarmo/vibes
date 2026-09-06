import { test, expect } from '@playwright/test';

test('composer search forwards image and attachment filters', async ({ page }) => {
    let requested;
    await page.route('**/search?*', async route => {
        requested = new URL(route.request().url());
        await route.fulfill({ contentType: 'application/json', body: '{"results":[]}' });
    });
    await page.goto('/');
    await page.getByTitle('Search', { exact: true }).click();
    await page.getByRole('checkbox', { name: 'Images', exact: true }).check();
    await page.getByRole('checkbox', { name: 'Attachments', exact: true }).check();
    const input = page.getByPlaceholder('Search (Enter to run)...');
    await input.fill('reference');
    await input.press('Enter');
    await expect.poll(() => requested?.searchParams.get('q')).toBe('reference');
    expect(requested.searchParams.get('has_images')).toBe('true');
    expect(requested.searchParams.get('has_attachments')).toBe('true');
});

test('search scope switches between current and all sessions', async ({ page }) => {
    const requests = [];
    await page.route('**/search?*', async route => {
        requests.push(new URL(route.request().url()));
        await route.fulfill({ contentType: 'application/json', body: '{"results":[]}' });
    });
    await page.goto('/');
    await page.getByTitle('Search', { exact: true }).click();
    const input = page.getByPlaceholder('Search (Enter to run)...');
    await input.fill('reference');
    await input.press('Enter');
    await expect.poll(() => requests.length).toBe(1);
    expect(requests[0].searchParams.get('session_id')).toBe('default');
    await page.getByRole('combobox', { name: 'Search scope' }).selectOption('all');
    await input.press('Enter');
    await expect.poll(() => requests.length).toBe(2);
    expect(requests[1].searchParams.has('session_id')).toBe(false);
});
