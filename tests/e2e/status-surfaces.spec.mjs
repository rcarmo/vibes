import { test, expect } from '@playwright/test';

// Surface values from deployed Piclaw classic 2.15.3: base.css,
// responsive.css and agent.css. These are CSS checks, not full pixel parity.
for (const width of [1280, 390]) {
    test(`classic status surfaces at ${width}px`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 844 });
        await page.goto('/');
        await page.evaluate(async () => {
            const { html, render } = await import('/static/js/vendor/preact-htm.js');
            const { AgentStatus } = await import('/static/js/components/status.js');
            const host = document.createElement('div');
            host.id = 'status-fixture';
            host.style.cssText = 'position:fixed;inset:0;z-index:9999;background:var(--bg-primary);padding:16px;overflow:auto';
            document.body.appendChild(host);
            render(html`<div style="max-width:868px;margin:auto">
                <h2>Status panes — synthetic UI fixture</h2>
                <${AgentStatus} status=${{ type: 'working', text: 'Reading workspace files' }}
                    thought=${'Checking the status pane styles against the deployed classic UI.'}
                    draft=${'The panes now share the classic border, radius and spacing rules.'}
                    pendingRequest=${{ tool_call: { title: 'Run tests' } }} />
                <div style="margin-top:16px"><${AgentStatus} status=${{ type: 'error', text: 'Example agent error' }} /></div>
            </div>`, host);
        });
        const fixture = page.locator('#status-fixture');
        await expect(fixture.locator('.agent-thinking')).toHaveCount(2);
        const styles = await fixture.evaluate(host => {
            const pick = (selector, keys) => {
                const style = getComputedStyle(host.querySelector(selector));
                return Object.fromEntries(keys.map(key => [key, style[key]]));
            };
            return {
                panel: pick('.agent-status-panel', ['gap', 'overflow']),
                status: pick('.agent-status', ['paddingTop', 'borderTopWidth', 'borderRadius', 'boxShadow']),
                thought: pick('.agent-thinking', ['paddingTop', 'paddingLeft', 'borderTopWidth', 'borderRadius', 'borderBottomColor', 'boxShadow']),
                error: pick('.agent-status-error', ['borderTopColor', 'borderRadius']),
                errorText: pick('.agent-status-error .agent-status-text', ['fontWeight']),
            };
        });
        expect(styles.panel).toEqual({ gap: width < 640 ? '3px' : '4px', overflow: 'visible' });
        expect(styles.status.paddingTop).toBe(width < 640 ? '6px' : '8px');
        expect(styles.status.borderTopWidth).toBe('1px');
        expect(styles.status.borderRadius).toBe('8px');
        expect(styles.status.boxShadow).not.toBe('none');
        expect(styles.thought.paddingTop).toBe(width < 640 ? '6px' : '7px');
        expect(styles.thought.paddingLeft).toBe(width < 640 ? '9px' : '10px');
        expect(styles.thought.borderTopWidth).toBe('1px');
        expect(styles.thought.borderRadius).toBe('8px');
        expect(styles.thought.borderBottomColor).toBe('rgba(0, 0, 0, 0)');
        expect(styles.thought.boxShadow).not.toBe('none');
        expect(styles.error.borderTopColor).toBe('rgba(220, 38, 38, 0.25)');
        expect(styles.error.borderRadius).toBe('8px');
        expect(styles.errorText.fontWeight).toBe('500');
        expect(await fixture.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
        await page.bringToFront();
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
        await page.screenshot({ path: testInfo.outputPath(`status-surfaces-${width}.png`) });
    });
}
