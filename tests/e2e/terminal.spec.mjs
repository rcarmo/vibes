import { test, expect } from '@playwright/test';

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
    await expect(page.locator('.terminal-panel')).toHaveCount(0);
    await expect(popup.locator('.xterm')).toBeVisible();
    await popup.locator('.xterm-helper-textarea').pressSequentially("printf 'state-%s\\n' \"$PARITY_TOKEN\"");
    await popup.locator('.xterm-helper-textarea').press('Enter');
    await expect(popup.getByTestId('terminal-output')).toContainText('state-preserved');
    await popup.close();
});
