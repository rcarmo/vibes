import { test, expect } from '@playwright/test';

for (const width of [1280, 390]) {
    test(`draft and thoughts follow classic tail overflow at ${width}px`, async ({ page }) => {
        await page.setViewportSize({ width, height: 844 });
        await page.goto('/');
        await page.evaluate(async () => {
            const { html, render } = await import('/static/js/vendor/preact-htm.js');
            const { AgentStatus } = await import('/static/js/components/status.js');
            const lines = Array.from({ length: 14 }, (_, i) => `line-${i + 1}`).join('\n');
            const host = document.createElement('div');
            host.id = 'overflow-fixture';
            document.body.appendChild(host);
            render(html`<${AgentStatus} status=${{ type: 'working', title: 'Working' }}
                draft=${{ text: `<internal>${lines}</internal>   `, totalLines: 14 }}
                thought=${{ text: lines, totalLines: 14 }} />`, host);
        });
        const fixture = page.locator('#overflow-fixture');
        for (const key of ['draft', 'thought']) {
            const panel = fixture.locator(`[data-panel-key="${key}"]`);
            const body = panel.locator('.agent-thinking-body');
            await expect(body).toContainText('line-6');
            await expect(body).toContainText('line-14');
            await expect(body).not.toContainText('line-5\n');
            await expect(body).not.toContainText('<internal>');
            await expect(panel.getByRole('button')).toContainText('more…');
            await expect(panel.getByRole('button')).toHaveAttribute('title', new RegExp(`Show more ${key}`, 'i'));
            expect(await body.evaluate(el => el.scrollTop)).toBeGreaterThanOrEqual(0);
            await panel.getByRole('button').click();
            await expect(panel).toHaveAttribute('data-expanded', 'true');
            await expect(panel.getByRole('button')).toContainText('less');
            await expect(body).toContainText('line-1');
        }
    });
}
