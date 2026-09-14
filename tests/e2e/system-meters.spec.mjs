import { test, expect } from '@playwright/test';

const fixture = () => ({ hostname: 'remote-box', platform: 'linux', scope: 'server-os', available: true, sampled_at: Date.now(),
  cpu_percent: 42, ram_percent: 64, cpu_series: [10, 25, 42], ram_series: [60, 62, 64],
  ram_used_bytes: 8 * 1024 ** 3, ram_total_bytes: 16 * 1024 ** 3,
  process_rss_bytes: 128 * 1024 ** 2, process_rss_series_bytes: [64 * 1024 ** 2, 128 * 1024 ** 2],
  buffer_cache_bytes: 1024 ** 3, buffer_cache_series_bytes: [1024 ** 3],
  swap_total_bytes: 1024 ** 3, swap_used_bytes: 256 * 1024 ** 2, swap_percent: 25, swap_series: [20, 25],
  vram_percent: null, vram_series: [] });

test('desktop server meters render real-shaped histories, optional GPU, collapse and keyboard restore', async ({ page }) => {
  await page.route('**/system/metrics', route => route.fulfill({ json: fixture() }));
  await page.goto('/');
  const hud = page.getByTestId('system-meters');
  await expect(hud).toHaveAttribute('data-state', 'ready');
  await expect(hud).toContainText('remote-box');
  for (const [row, value] of [['cpu','42%'],['ram','64%'],['rss','128M'],['buf','1.0G'],['swap','25%']]) {
    await expect(hud.locator(`.system-meters-row.${row}`)).toContainText(value);
    await expect(hud.locator(`.system-meters-row.${row} path`)).toHaveAttribute('d', /^M /);
  }
  await expect(hud.locator('.vram')).toHaveCount(0);
  const collapse = page.getByRole('button', { name: 'Collapse server resource meters' });
  await expect(collapse).toHaveAttribute('title', /not browser or inference-server/);
  await collapse.click();
  await expect(hud).toHaveClass(/is-collapsed/);
  await page.reload();
  const expand = page.getByRole('button', { name: 'Show server resource meters' });
  await expect(expand).toHaveAttribute('aria-expanded', 'false');
  await expand.focus(); await page.keyboard.press('Enter');
  await expect(hud).not.toHaveClass(/is-collapsed/);
  await page.getByRole('button', { name: 'Quick actions', exact: true }).click();
  await page.getByRole('combobox', { name: 'Search quick actions' }).fill('server resource');
  await page.keyboard.press('Enter');
  await expect(hud).toHaveClass(/is-collapsed/);
});

test('GPU only shown with available telemetry; errors clear stale numbers and recover', async ({ page }) => {
  let mode = 'gpu';
  await page.route('**/system/metrics', route => {
    if (mode === 'error') return route.fulfill({ status: 503, json: { error: 'unavailable' } });
    const data = fixture();
    if (mode === 'gpu') Object.assign(data, { vram_percent: 75, vram_total_bytes: 1024 ** 3, vram_used_bytes: 768 * 1024 ** 2, vram_series: [50, 75], gpu_provider: 'Linux DRM' });
    if (mode === 'stale') data.sampled_at = Date.now() - 60000;
    return route.fulfill({ json: data });
  });
  await page.goto('/');
  const hud = page.getByTestId('system-meters');
  await expect(hud.locator('.vram')).toContainText('75%');
  mode = 'error';
  await expect(hud).toHaveAttribute('data-state', 'unavailable', { timeout: 8000 });
  await expect(hud.locator('.cpu')).toContainText('—');
  await expect(hud.locator('.vram')).toHaveCount(0);
  mode = 'stale';
  await expect(hud).toHaveAttribute('data-state', 'unavailable');
  mode = 'good';
  await expect(hud.locator('.cpu')).toContainText('42%', { timeout: 8000 });
});

test('mobile compact server summary does not cover composer or exceed viewport', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/system/metrics', route => route.fulfill({ json: fixture() }));
  await page.goto('/');
  const hud = page.getByTestId('system-meters');
  await expect(hud.locator('.system-meters-compact-summary')).toContainText('CPU 42% • RAM 64%');
  const meter = await hud.boundingBox();
  const compose = await page.locator('.compose-box').boundingBox();
  expect(meter.x).toBeGreaterThanOrEqual(0);
  expect(meter.x + meter.width).toBeLessThanOrEqual(390);
  expect(meter.y + meter.height).toBeLessThan(compose.y);
  await page.locator('.compose-box textarea').fill('composition unaffected');
  await expect(page.locator('.compose-box textarea')).toHaveValue('composition unaffected');
  await page.screenshot({ path: info.outputPath('mobile-meters.png') });
});

test('polling serializes slow requests, resumes from hidden tab, cleans up on popout', async ({ page }) => {
  let release, requests = 0;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/system/metrics', async route => { requests++; if (requests === 1) await gate; await route.fulfill({ json: fixture() }); });
  await page.goto('/');
  await expect.poll(() => requests).toBe(1);
  await page.waitForTimeout(2400); expect(requests).toBe(1);
  release(); await expect(page.getByTestId('system-meters')).toHaveAttribute('data-state', 'ready');
  await page.evaluate(() => { Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' }); document.dispatchEvent(new Event('visibilitychange')); });
  const paused = requests;
  await page.waitForTimeout(2400); expect(requests).toBe(paused);
  await page.evaluate(() => { Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' }); document.dispatchEvent(new Event('visibilitychange')); });
  await expect.poll(() => requests).toBeGreaterThan(paused);
  await page.goto('/?terminal=1');
  await expect(page.getByTestId('system-meters')).toHaveCount(0);
});

for (const width of [640, 1440]) {
  test(`meters layout at ${width}px stays above composer and does not hide cancel`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route('**/system/metrics', route => route.fulfill({ json: fixture() }));
    await page.route('**/agents/status?*', route => route.fulfill({ json: { busy: true, active_turns: [{ turn_id: 'meter-turn', thread_id: 1, agent_id: 'default', last_status: { type: 'thinking', title: 'Thinking…' } }] } }));
    await page.goto('/');
    const hud = page.getByTestId('system-meters');
    await expect(hud).toHaveAttribute('data-state', 'ready');
    await expect(page.getByTestId('stop-button')).toBeVisible();
    const box = await hud.boundingBox();
    const compose = await page.locator('.compose-box').boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width);
    expect(box.y + box.height).toBeLessThan(compose.y);
    await page.screenshot({ path: info.outputPath(`meters-${width}.png`) });
  });
}
