import { test, expect } from '@playwright/test';

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z2SMAAAAASUVORK5CYII=', 'base64');
const row = (id, content, ids, blocks, session_id = 'default') => ({ id, timestamp: new Date().toISOString(), reply_count: 0,
  data: { type: 'agent_response', content, media_ids: ids, content_blocks: blocks, session_id, intermediate: true } });
const image = (id, name = 'chart.png') => ({ type: 'image', media_id: id, name, content_type: 'image/png' });
async function media(page) {
  await page.route('**/media/*', route => route.fulfill({ contentType: 'image/png', body: png }));
  await page.route('**/media/*/thumbnail', route => route.fulfill({ contentType: 'image/png', body: png }));
  await page.route('**/media/*/info', route => route.fulfill({ json: { id: 77, filename: 'chart.png', content_type: 'image/png', metadata: { width: 1, height: 1, size: png.length } } }));
}

test('immediate agent attachment appears without final text, retains turn and survives reload', async ({ page }, info) => {
  await page.addInitScript(() => {
    class Stream { constructor() { this.listeners = new Map(); this.readyState = 1; window.stream = this; } addEventListener(t, fn) { this.listeners.set(t, fn); } close() {} }
    window.EventSource = Stream;
    window.emit = (type, data) => window.stream.listeners.get(type)?.({ data: JSON.stringify(data) });
  });
  await media(page);
  let posts = [];
  await page.route('**/timeline?*', route => route.fulfill({ json: { posts, has_more: false } }));
  await page.route('**/agents/status?*', route => route.fulfill({ json: { busy: true, active_turns: [{ turn_id: 'image-turn', thread_id: 1, last_status: { type: 'thinking', title: 'Drawing' } }] } }));
  await page.goto('/');
  await expect(page.getByTestId('stop-button')).toBeVisible();
  await page.locator('.compose-box textarea').fill('keep draft');
  const picture = row(991, '', [77], [image(77)]);
  posts = [picture];
  await page.evaluate(p => window.emit('new_post', p), picture);
  const post = page.locator('#post-991');
  await expect(post).toHaveClass(/agent/);
  await expect(post.locator('img[src*="/media/77"]')).toBeVisible();
  await expect(page.getByTestId('stop-button')).toBeVisible();
  await expect(page.locator('.compose-box textarea')).toHaveValue('keep draft');
  // Repeated SSE is idempotent, other sessions cannot inject their row.
  await page.evaluate(p => window.emit('new_post', p), picture);
  await page.evaluate(p => window.emit('new_post', p), row(992, '', [78], [image(78)], 'other'));
  await expect(post).toHaveCount(1); await expect(page.locator('#post-992')).toHaveCount(0);
  await page.reload();
  await expect(post.locator('img[src*="/media/77"]')).toBeVisible();
  await expect(page.locator('.compose-box textarea')).toHaveValue('keep draft');
  await page.screenshot({ path: info.outputPath('agent-image.png') });
});

test('numeric inline refs map by ID, bare refs keep image cards, unknown refs never borrow another image', async ({ page }) => {
  await media(page);
  const posts = [row(991, '![second](attachment:78)', [77, 78], [image(77, 'first.png'), image(78, 'second.png')]),
    row(992, 'See attachment:77', [77], [image(77)]),
    row(993, '![unknown](attachment:999)', [77], [image(77)])];
  await page.route('**/timeline?*', route => route.fulfill({ json: { posts, has_more: false } }));
  await page.goto('/');
  await expect(page.locator('#post-991 img[alt="second"]')).toHaveAttribute('src', '/media/78');
  await expect(page.locator('#post-991 img[src*="/media/77"]')).toBeVisible();
  await expect(page.locator('#post-992 img[src*="/media/77"]')).toBeVisible();
  await expect(page.locator('#post-993 img[src*="/media/77"]')).toBeVisible();
  await expect(page.locator('#post-993 img[alt="unknown"]')).not.toHaveAttribute('src', '/media/77');
});

test('file attachments have download cards and mobile images fit the message', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await media(page);
  await page.route('**/media/79/info', route => route.fulfill({ json: { id: 79, filename: 'drawing.svg', content_type: 'application/octet-stream', metadata: { size: 42 } } }));
  await page.route('**/timeline?*', route => route.fulfill({ json: { posts: [row(991, '', [77, 79], [image(77), { type: 'file', name: 'drawing.svg', media_id: 79 }])], has_more: false } }));
  await page.goto('/');
  await expect(page.locator('#post-991').getByText('drawing.svg', { exact: true }).first()).toBeVisible();
  const img = page.locator('#post-991 img[src*="/media/77"]');
  await expect(img).toBeVisible();
  const box = await img.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(390);
  await expect(page.locator('#post-991 img[src*="/media/79"]')).toHaveCount(0);
});
