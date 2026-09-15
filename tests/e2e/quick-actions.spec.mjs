import { test, expect } from '@playwright/test';

const dialog = page => page.getByRole('dialog', { name: 'Quick actions', exact: true });
const input = page => page.getByRole('combobox', { name: 'Search quick actions' });
const option = (page, key) => page.locator(`[data-action-key="${key}"]`);
async function ready(page) {
  await page.goto('/');
  await expect(page.locator('.compose-box textarea')).toBeVisible();
  await expect(page.locator('.workspace-toggle-tab')).toBeVisible();
}
async function open(page) {
  if (!await page.getByRole('button', { name: 'Quick actions', exact: true }).isVisible()) await page.getByRole('button', { name: 'Show workspace', exact: true }).click();
  await page.getByRole('button', { name: 'Quick actions', exact: true }).click();
  await expect(input(page)).toBeFocused();
}
async function timelineFocus(page) {
  await page.locator('.timeline').evaluate(el => { el.tabIndex = -1; el.focus(); });
}

test('timeline typing opens grouped actions; filtering, wrapping arrows, Escape and focus restore', async ({ page }) => {
  await ready(page);
  await timelineFocus(page);
  await page.keyboard.type('model');
  await expect(input(page)).toHaveValue('model');
  await expect(input(page)).toBeFocused();
  await expect(option(page, 'slash:/model')).toHaveClass(/active/);
  await input(page).fill('');
  await expect(page.locator('.timeline-quick-actions-section')).toHaveText(['Agents', 'Workspace', 'Slash commands']);
  const options = page.locator('.timeline-quick-actions-item');
  await expect(options.first()).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('ArrowUp');
  await expect(options.last()).toHaveAttribute('aria-selected', 'true');
  await page.keyboard.press('ArrowDown');
  await expect(options.first()).toHaveAttribute('aria-selected', 'true');
  await input(page).fill('zz-no-such-action');
  await expect(page.getByText('No quick actions match.')).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(dialog(page)).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog(page)).toHaveCount(0);
  await expect(page.locator('.timeline')).toBeFocused();
});

test('typing in composer, search, editable fields and modal does not open actions; modifiers and IME are safe', async ({ page }) => {
  await ready(page);
  const compose = page.locator('.compose-box textarea');
  await compose.fill(''); await compose.pressSequentially('hello');
  await expect(dialog(page)).toHaveCount(0);
  await page.getByTitle('Search', { exact: true }).click();
  await compose.pressSequentially('find');
  await expect(dialog(page)).toHaveCount(0);
  await page.getByTitle('Close search', { exact: true }).click();
  await timelineFocus(page);
  await page.keyboard.press('Control+k'); await page.keyboard.press('Meta+k');
  await page.locator('.timeline').dispatchEvent('keydown', { key: 'k', isComposing: true });
  await expect(dialog(page)).toHaveCount(0);
  await page.evaluate(() => {
    const editable = document.createElement('div'); editable.contentEditable = 'true'; editable.id = 'editable-test';
    document.querySelector('.timeline').appendChild(editable); editable.focus();
  });
  await page.keyboard.type('text');
  await expect(dialog(page)).toHaveCount(0);
  await page.evaluate(() => {
    const modal = document.createElement('dialog'); modal.id = 'modal-test'; document.body.appendChild(modal); modal.showModal();
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', bubbles: true }));
  });
  await expect(dialog(page)).toHaveCount(0);
});

test('command selection prefills without sending or losing draft media, references or search state', async ({ page }) => {
  let posts = 0;
  await page.route('**/agent/default/message', route => { posts++; return route.fulfill({ json: { status: 'ok' } }); });
  await page.addInitScript(() => {
    // Draft references use the same durable store as real workspace selections.
    localStorage.setItem('vibes_compose_draft:default', JSON.stringify({ text: '', fileRefs: ['README.md'], folderRefs: ['src'], messageRefs: [] }));
  });
  await ready(page);
  await page.locator('.compose-box textarea').fill('existing draft');
  await page.locator('.compose-box input[type="file"]').setInputFiles({ name: 'draft.txt', mimeType: 'text/plain', buffer: Buffer.from('keep me') });
  await expect(page.locator('.compose-box').getByText('draft.txt', { exact: true })).toBeVisible();
  await open(page);
  await input(page).fill('theme');
  await page.keyboard.press('Enter');
  await expect(dialog(page)).toHaveCount(0);
  await expect(page.locator('.compose-box textarea')).toHaveValue('/theme existing draft');
  await expect(page.locator('.compose-box textarea')).toBeFocused();
  await expect(page.locator('.compose-box').getByText('draft.txt', { exact: true })).toBeVisible();
  await expect(page.locator('.compose-box').getByText('README.md', { exact: true })).toBeVisible();
  expect(posts).toBe(0);
  await page.getByTitle('Search', { exact: true }).click();
  await page.locator('.compose-box textarea').fill('search text');
  await open(page); await input(page).fill('context');
  await option(page, 'slash:/context').click();
  await expect(page.locator('.compose-box textarea')).toHaveValue('/context /theme existing draft');
  expect(posts).toBe(0);
});

test('session actions switch via pointer and keyboard while preserving separate drafts; archive filtered', async ({ page, request }) => {
  const title = `quick-${Date.now()}`;
  const a = (await (await request.post('/sessions', { data: { name: title } })).json()).session;
  const archived = (await (await request.post('/sessions', { data: { name: 'archived-quick' } })).json()).session;
  await request.patch(`/sessions/${archived.id}`, { data: { archived: true } });
  await ready(page);
  await page.locator('.compose-box textarea').fill('default draft');
  await open(page);
  await expect(option(page, `session:${archived.id}`)).toHaveCount(0);
  await input(page).fill(title);
  await option(page, `session:${a.id}`).click();
  await expect(page.getByTestId('session-switcher')).toContainText(title);
  await expect(page.locator('.compose-box textarea')).toHaveValue('');
  await page.locator('.compose-box textarea').fill('other draft');
  await open(page); await input(page).fill('@default'); await page.keyboard.press('Enter');
  await expect(page.getByTestId('session-switcher')).not.toContainText(title);
  await expect(page.locator('.compose-box textarea')).toHaveValue('default draft');
  await request.delete(`/sessions/${a.id}`); await request.delete(`/sessions/${archived.id}`);
});

test('workspace and capability-gated terminal actions use real controls', async ({ page }) => {
  await ready(page); await open(page);
  const initial = await page.locator('.workspace-toggle-tab').getAttribute('aria-expanded');
  await input(page).fill('workspace'); await option(page, 'workspace:toggle-workspace').click();
  await expect(page.locator('.workspace-toggle-tab')).toHaveAttribute('aria-expanded', initial === 'true' ? 'false' : 'true');
  await open(page); await input(page).fill('terminal'); await option(page, 'workspace:open-terminal').click();
  await expect(page.locator('.terminal-panel')).toBeVisible();
  await expect(dialog(page)).toHaveCount(0);
});

test('mobile launcher, focus trap, outside dismiss and unsupported actions absent', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/terminal/session', route => route.fulfill({ json: { enabled: false } }));
  await ready(page); await open(page);
  await expect(option(page, 'workspace:open-terminal')).toHaveCount(0);
  expect((await page.locator('.timeline-quick-actions-item-title').allTextContents()).join(' ')).not.toMatch(/VNC|Settings|Pop out/);
  const box = await dialog(page).boundingBox(); expect(box.width).toBeLessThanOrEqual(390); expect(box.x).toBeGreaterThanOrEqual(0);
  await page.keyboard.press('Shift+Tab');
  await expect(page.locator('.timeline-quick-actions-item').last()).toBeFocused();
  await page.keyboard.press('Tab'); await expect(input(page)).toBeFocused();
  await page.getByRole('button', { name: 'Close quick actions' }).click();
  await expect(page.getByRole('button', { name: 'Quick actions', exact: true })).toBeFocused();
  await open(page); await page.mouse.click(2, 2); await expect(dialog(page)).toHaveCount(0);
});

test('command catalogue requests track selected session and late prior responses are ignored', async ({ page, request }) => {
  const a = (await (await request.post('/sessions', { data: { name: `scoped-quick-${Date.now()}` } })).json()).session;
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const seen = [];
  await page.route('**/agent/commands?*', async route => {
    const id = new URL(route.request().url()).searchParams.get('session_id'); seen.push(id);
    if (id === 'default') await gate;
    await route.fulfill({ json: { commands: [{ name: id === 'default' ? '/old-private' : '/new-private', description: id }] } });
  });
  await ready(page); await open(page); await input(page).fill(a.name); await option(page, `session:${a.id}`).click();
  await expect(page.getByTestId('session-switcher')).toContainText(a.name);
  await open(page); await input(page).fill('new-private'); await expect(option(page, 'slash:/new-private')).toBeVisible();
  release();
  await input(page).fill('old-private'); await expect(page.getByText('No quick actions match.')).toBeVisible();
  expect(seen).toContain(a.id); expect(seen).toContain('default');
  await request.delete(`/sessions/${a.id}`);
});
