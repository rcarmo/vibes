// @ts-check
import { test, expect } from '@playwright/test';

async function mount(page) {
  await page.goto('/');
  await page.evaluate(async () => {
    const { html, render } = await import('/static/js/vendor/preact-htm.js');
    const { AgentStatus } = await import('/static/js/components/status.js');
    const host = document.createElement('div'); host.id = 'thought-fixture'; document.body.appendChild(host);
    window.__thought = 'line-1\nline-2\nline-3\nline-4\nline-5\nline-6\nline-7\nline-8\nline-9\nline-10';
    window.__toggles = [];
    window.__renderThought = () => render(html`<${AgentStatus} status=${{type:'thinking',title:'Thinking'}} thought=${{text:window.__thought,totalLines:10,fullText:window.__thought}} turnId="turn-1" onPanelExpandedChange=${(key, value) => window.__toggles.push([key,value])} />`, host);
    window.__renderThought();
  });
}

test('@ux-thoughts-001 collapsed panel exposes state and clipped overflow', async ({ page }) => {
  await mount(page); const panel=page.locator('#thought-fixture [data-panel-key="thought"]');
  await expect(panel).toHaveAttribute('data-expanded','false'); await expect(panel).toHaveAttribute('data-collapsible','true');
  const text = await panel.locator('.agent-thinking-body').innerText();
  expect(text).not.toMatch(/(^|\s)line-1(\s|$)/); expect(text).toContain('line-10');
});

test('@ux-thoughts-002 collapsed content updates independently', async ({ page }) => {
  await mount(page); await page.evaluate(() => { window.__thought='updated thought'; window.__renderThought(); });
  const panel=page.locator('#thought-fixture [data-panel-key="thought"]'); await expect(panel).toHaveAttribute('data-expanded','false'); await expect(panel).toContainText('updated thought');
});

test('@ux-thoughts-003 disclosure toggles and reports callback state', async ({ page }) => {
  await mount(page); const panel=page.locator('#thought-fixture [data-panel-key="thought"]'), button=panel.getByRole('button');
  await button.click(); await expect(panel).toHaveAttribute('data-expanded','true'); await expect.poll(() => page.evaluate(() => window.__toggles.some(x=>x[0]==='thought'&&x[1]===true))).toBe(true);
  await button.click(); await expect(panel).toHaveAttribute('data-expanded','false');
});

test('@ux-thoughts-005 disclosure preserves streamed text', async ({ page }) => {
  await mount(page); const panel=page.locator('#thought-fixture [data-panel-key="thought"]'), button=panel.getByRole('button');
  await button.click(); await expect(panel).toContainText('line-1'); await expect(panel).toContainText('line-10');
  await button.click(); await button.click(); await expect(panel).toContainText('line-1'); await expect(panel).toContainText('line-10');
});
