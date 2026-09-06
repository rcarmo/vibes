import { test, expect } from '@playwright/test';

async function openEditor(page) {
    const sidebar = page.locator('.workspace-sidebar');
    if (!await sidebar.isVisible()) await page.locator('.workspace-toggle-tab').click();
    await page.locator('.workspace-row .workspace-label').filter({ hasText: 'README.md' }).first().click();
    await page.locator('.workspace-edit').click();
    await expect(page.locator('.editor-stack')).toBeVisible();
}

test('terminal executes and hands the same shell to a popout', async ({ page }) => {
    await page.goto('/');
    await page.getByTitle('Open terminal', { exact: true }).click();
    await expect(page.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    await page.locator('.xterm-helper-textarea').pressSequentially("export PARITY_TOKEN=preserved; printf 'terminal-%s\\n' ready");
    await page.locator('.xterm-helper-textarea').press('Enter');
    await expect(page.getByTestId('terminal-output')).toContainText('terminal-ready');
    await expect(page.locator('.dock-panel > .dock-panel-header .dock-panel-title')).toHaveText('Terminal');
    await expect(page.locator('.dock-panel-actions .dock-panel-action svg')).toBeVisible();
    await expect(page.locator('.dock-panel > .dock-panel-body .terminal-pane-xterm')).toBeVisible();
    const popupPromise = page.waitForEvent('popup');
    await page.getByTitle('Open terminal in window').click();
    const popup = await popupPromise;
    await expect(popup.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    await expect(page.getByRole('heading', { name: 'Terminal detached' })).toBeVisible();
    await expect(popup.locator('.xterm')).toBeVisible();
    await popup.locator('.xterm-helper-textarea').pressSequentially("printf 'state-%s\\n' \"$PARITY_TOKEN\"");
    await popup.locator('.xterm-helper-textarea').press('Enter');
    await expect(popup.getByTestId('terminal-output')).toContainText('state-preserved');
    await page.getByRole('button', { name: 'Reattach here' }).click();
    await expect(page.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    await page.locator('.xterm-helper-textarea').pressSequentially("printf 'return-%s\\n' \"$PARITY_TOKEN\"");
    await page.locator('.xterm-helper-textarea').press('Enter');
    await expect(page.getByTestId('terminal-output')).toContainText('return-preserved');
    await expect.poll(() => popup.isClosed()).toBe(true);
});

test('terminal splitter supports keyboard resizing', async ({ page }) => {
    await page.goto('/');
    await page.getByTitle('Open terminal', { exact: true }).click();
    await openEditor(page);
    const splitter = page.getByRole('separator', { name: 'Resize terminal' });
    const initial = Number(await splitter.getAttribute('aria-valuenow'));
    await splitter.focus();
    await splitter.press('ArrowUp');
    await expect(splitter).toHaveAttribute('aria-valuenow', String(initial + 20));
    await splitter.press('ArrowDown');
    await expect(splitter).toHaveAttribute('aria-valuenow', String(initial));
    await page.getByRole('button', { name: 'Hide terminal', exact: true }).click();
    await expect(page.locator('.terminal-panel')).toHaveCount(0);
});

test('closed popout reconnects within grace without losing shell state', async ({ page }) => {
    await page.goto('/');
    await page.getByTitle('Open terminal', { exact: true }).click();
    await expect(page.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    await page.locator('.xterm-helper-textarea').pressSequentially('export RECOVERY_TOKEN=retained');
    await page.locator('.xterm-helper-textarea').press('Enter');
    const popupPromise = page.waitForEvent('popup');
    await page.getByTitle('Open terminal in window').click();
    const popup = await popupPromise;
    await expect(popup.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    await popup.close();
    await expect.poll(() => page.evaluate(async () => (await (await fetch('/terminal/session')).json()).connected_clients)).toBe(0);
    await page.getByRole('button', { name: 'Reattach here' }).click();
    await expect(page.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    await page.locator('.xterm-helper-textarea').pressSequentially("printf 'recover-%s\\n' \"$RECOVERY_TOKEN\"");
    await page.locator('.xterm-helper-textarea').press('Enter');
    await expect(page.getByTestId('terminal-output')).toContainText('recover-retained');
});

test('expired popout session clearly starts a new shell', async ({ page }) => {
    test.setTimeout(45000);
    await page.goto('/');
    await page.getByTitle('Open terminal', { exact: true }).click();
    await expect(page.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    const popupPromise = page.waitForEvent('popup');
    await page.getByTitle('Open terminal in window').click();
    const popup = await popupPromise;
    await expect(popup.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    await popup.close();
    await expect.poll(() => page.evaluate(async () => (await (await fetch('/terminal/session')).json()).active), { timeout: 20000 }).toBe(false);
    await page.getByRole('button', { name: 'Reattach here' }).click();
    await expect(page.getByRole('alert')).toContainText('started a new shell');
    await expect(page.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
});

for (const [name, viewport] of [
    ['desktop', { width: 1440, height: 1000 }],
    ['mobile', { width: 390, height: 844 }],
]) {
    test(`terminal ${name} layout and screenshot`, async ({ page }, testInfo) => {
        await page.setViewportSize(viewport);
        await page.goto('/');
        await page.getByTitle('Open terminal', { exact: true }).click();
        await expect(page.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
        await page.locator('.xterm-helper-textarea').pressSequentially("printf 'Vibes terminal verification\\n'");
        await page.locator('.xterm-helper-textarea').press('Enter');
        await expect(page.getByTestId('terminal-output')).toContainText('Vibes terminal verification');
        const box = await page.locator('.terminal-panel').boundingBox();
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
        expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1);
        await expect(page.getByRole('button', { name: 'Hide terminal', exact: true })).toBeVisible();
        await page.screenshot({ path: testInfo.outputPath(`terminal-${name}.png`), fullPage: true });
    });
}

test('terminal height stays bounded after viewport shrink and keyboard resize', async ({ page }) => {
    await page.setViewportSize({ width: 1200, height: 1000 });
    await page.goto('/');
    await page.getByTitle('Open terminal', { exact: true }).click();
    await expect(page.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    await openEditor(page);
    const splitter = page.getByRole('separator', { name: 'Resize terminal' });
    await splitter.focus();
    const before = Number(await splitter.getAttribute('aria-valuenow'));
    await splitter.press('ArrowUp');
    await expect(splitter).toHaveAttribute('aria-valuenow', String(before + 20));
    await page.setViewportSize({ width: 844, height: 390 });
    await expect.poll(async () => Number(await splitter.getAttribute('aria-valuenow'))).toBeLessThanOrEqual(330);
    const box = await page.locator('.terminal-panel').boundingBox();
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(391);
    await expect(page.getByRole('button', { name: 'Hide terminal', exact: true })).toBeVisible();
});

for (const width of [1440, 390]) {
    test(`shared dock does not cover composer at width ${width}`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto('/');
        await page.getByTitle('Open terminal', { exact: true }).click();
        await expect(page.locator('.editor-pane-container > .terminal-panel')).toBeVisible();
        const terminal = await page.locator('.terminal-panel').boundingBox();
        const compose = await page.locator('.compose-input-main textarea').boundingBox();
        expect(terminal.x + terminal.width <= compose.x + 1 || terminal.y + terminal.height <= compose.y + 1).toBe(true);
    });
}

test('Control Backquote toggles dock and preserves shell during grace', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTitle('Open terminal', { exact: true })).toBeVisible();
    await page.keyboard.press('Control+Backquote');
    await expect(page.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    await page.locator('.xterm-helper-textarea').pressSequentially('export SHORTCUT_TOKEN=kept');
    await page.locator('.xterm-helper-textarea').press('Enter');
    await page.keyboard.press('Control+Backquote');
    await expect(page.locator('.terminal-panel')).toHaveCount(0);
    await page.keyboard.press('Control+Backquote');
    await expect(page.locator('.terminal-status')).toHaveText('Connected', { timeout: 15000 });
    await page.locator('.xterm-helper-textarea').pressSequentially('echo $SHORTCUT_TOKEN');
    await page.locator('.xterm-helper-textarea').press('Enter');
    await expect(page.getByTestId('terminal-output')).toContainText('kept');
});
