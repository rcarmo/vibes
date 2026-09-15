import { test, expect } from '@playwright/test';

async function seed(page, id = 'default', markdown = '- [x] Inspect reference\n- [-] Port sidebar\n- [ ] Verify tablet layout') {
    const response = await page.request.get(`/sessions/${id}/plan`);
    const current = await response.json();
    const saved = await page.request.put(`/sessions/${id}/plan`, { data: { markdown, expected_revision: current.revision } });
    expect(saved.ok()).toBe(true);
    return saved.json();
}
async function openPlan(page) {
    await page.locator('.plan-sidebar-toggle').click();
    await expect(page.locator('.plan-sidebar-root')).toHaveClass(/open/);
    await expect(page.locator('.plan-sidebar-editor .cm-content')).toBeVisible();
    await expect(page.locator('.plan-sidebar-status')).toContainText(/Loaded|Updated/);
    // Wait for the real drawer transition, rather than measuring its intermediate position.
    await expect.poll(() => page.locator('.plan-sidebar-panel').evaluate(node => Math.abs(node.getBoundingClientRect().right - innerWidth))).toBeLessThan(1);
}
async function replacePlan(page, text) {
    const editor = page.locator('.plan-sidebar-editor .cm-content');
    await editor.click(); await page.keyboard.press('ControlOrMeta+A');
    await page.keyboard.insertText(text);
}

test('Plan sidebar persists through reload and receives real session-scoped SSE changes', async ({ page }) => {
    await seed(page);
    await page.goto('/'); await openPlan(page);
    await expect(page.locator('.plan-sidebar-progress-label')).toHaveText('1/3 items complete');
    await expect(page.locator('.plan-sidebar-progress-percent')).toHaveText('33%');
    await expect(page.locator('.plan-sidebar-editor .plan-sidebar-cm-checkbox-current')).toHaveText('[-]');
    await replacePlan(page, '- [x] Saved from browser');
    await page.locator('.plan-sidebar-save').click();
    await expect(page.locator('.plan-sidebar-status')).toContainText('Saved');
    expect((await (await page.request.get('/sessions/default/plan')).json()).markdown).toBe('- [x] Saved from browser');
    await page.reload();
    await expect(page.locator('.cm-content')).toContainText('Saved from browser');
    await seed(page, 'default', '- [-] External API update');
    await expect(page.locator('.cm-content')).toContainText('External API update');
    await expect(page.locator('.plan-sidebar-status')).toContainText('Updated from');
    const other = (await (await page.request.post('/sessions', { data: { name: 'Other plan' } })).json()).session.id;
    await seed(page, other, '- [ ] Wrong session');
    await expect(page.locator('.cm-content')).not.toContainText('Wrong session');
    await page.keyboard.press('Escape');
    await expect(page.locator('.plan-sidebar-root')).not.toHaveClass(/open/);
    expect(await page.locator('.plan-sidebar-panel').evaluate(node => node.inert)).toBe(true);
});

test('remote Plan updates cannot overwrite dirty text, stale save fails and refresh confirms discard', async ({ page }) => {
    await seed(page);
    await page.goto('/'); await openPlan(page);
    await replacePlan(page, '- [ ] Unsaved local changes');
    await seed(page, 'default', '- [x] Concurrent edit');
    await expect(page.locator('.plan-sidebar-status')).toContainText('changed remotely');
    await expect(page.locator('.cm-content')).toContainText('Unsaved local changes');
    await page.locator('.plan-sidebar-save').click();
    await expect(page.locator('.plan-sidebar-status')).toContainText('Plan changed');
    expect((await (await page.request.get('/sessions/default/plan')).json()).markdown).toBe('- [x] Concurrent edit');
    page.once('dialog', dialog => dialog.dismiss());
    await page.locator('.plan-sidebar-refresh').click();
    await expect(page.locator('.cm-content')).toContainText('Unsaved local changes');
    page.once('dialog', dialog => dialog.accept());
    await page.locator('.plan-sidebar-refresh').click();
    await expect(page.locator('.cm-content')).toContainText('Concurrent edit');
});

test('session switching preserves unsaved Plan drafts without copying them to another session', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.addInitScript(() => localStorage.setItem('workspaceOpen', 'false'));
    await seed(page);
    const id = (await (await page.request.post('/sessions', { data: { name: 'Plan second' } })).json()).session.id;
    await seed(page, id, '- [ ] Second session only');
    await page.goto('/'); await openPlan(page);
    await replacePlan(page, '- [ ] First session draft');
    // Plan is nonmodal and overlays the pointer target; keyboard switching remains available.
    await page.getByTestId('session-switcher').focus();
    await page.keyboard.press('Enter');
    await page.locator(`#session-option-${id}`).focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('.plan-sidebar-subtitle')).toContainText(id);
    await expect(page.locator('.cm-content')).toContainText('Second session only');
    await expect(page.locator('.cm-content')).not.toContainText('First session draft');
    await page.getByTestId('session-switcher').focus();
    await page.keyboard.press('Enter');
    await page.locator('#session-option-default').focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('.cm-content')).toContainText('First session draft');
    await expect(page.locator('.plan-sidebar-subtitle')).toContainText('unsaved');
    await page.locator('.plan-sidebar-save').click();
    await expect(page.locator('.plan-sidebar-status')).toContainText('Saved');
});

test('late save preserves newer Plan edits, submission is scoped and keeps composer draft', async ({ page }) => {
    await seed(page);
    let release;
    await page.route('**/sessions/default/plan', async route => {
        if (route.request().method() !== 'PUT') return route.continue();
        await new Promise(resolve => { release = resolve; });
        await route.continue();
    });
    await page.goto('/'); await openPlan(page);
    await replacePlan(page, '- [ ] First edit');
    await page.locator('.plan-sidebar-save').click();
    await expect.poll(() => Boolean(release)).toBe(true);
    await replacePlan(page, '- [-] Newer edit');
    release();
    await expect(page.locator('.plan-sidebar-status')).toContainText('newer changes are unsaved');
    await expect(page.locator('.cm-content')).toContainText('Newer edit');
    await page.unroute('**/sessions/default/plan');
    let sent;
    await page.route('**/agent/default/message', route => { sent = route.request().postDataJSON(); return route.fulfill({ json: { status: 'ok' } }); });
    await page.locator('.compose-box textarea').fill('Keep this composer draft');
    await page.locator('.plan-sidebar-submit').click();
    await expect(page.locator('.plan-sidebar-status')).toHaveText('Submitted to model.');
    expect(sent.session_id).toBe('default');
    expect(sent.content).toContain('- [-] Newer edit');
    await expect(page.locator('.compose-box textarea')).toHaveValue('Keep this composer draft');
});

for (const width of [390, 820, 1440]) test(`Plan drawer is usable at ${width}px without layout masks`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await seed(page);
    await page.goto('/'); await openPlan(page);
    const panel = await page.locator('.plan-sidebar-panel').boundingBox();
    expect(panel.x).toBeGreaterThanOrEqual(0);
    expect(panel.x + panel.width).toBeLessThanOrEqual(width + 1);
    await expect(page.locator('.plan-sidebar-save')).toBeVisible();
    await expect(page.locator('.plan-sidebar-submit')).toBeVisible();
    await page.locator('.plan-sidebar-toggle').click();
    await expect(page.locator('.plan-sidebar-root')).not.toHaveClass(/open/);
});
