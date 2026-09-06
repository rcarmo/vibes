// @ts-check
import { test, expect } from '@playwright/test';

// Wait for the SPA to fully hydrate
async function waitForApp(page) {
    await page.goto('/');
    // Wait for the app shell to render (workspace toggle is always present)
    await page.waitForSelector('.app-shell', { timeout: 10_000 });
}

// Ensure the workspace sidebar is visible
async function ensureWorkspaceOpen(page) {
    const sidebar = page.locator('.workspace-sidebar');
    if (!(await sidebar.isVisible().catch(() => false))) {
        await page.locator('.workspace-toggle-tab').click();
        await sidebar.waitFor({ state: 'visible', timeout: 5000 });
    }
}

// Click a file in the workspace tree by name
async function clickFileInTree(page, filename) {
    await ensureWorkspaceOpen(page);
    // Find the row with this file label
    const row = page.locator('.workspace-row .workspace-label', { hasText: filename }).first();
    await row.waitFor({ state: 'visible', timeout: 5000 });
    await row.click();
}

// Open a file in the editor via the workspace "Edit" button
async function openFileInEditor(page, filename) {
    await clickFileInTree(page, filename);
    // Wait for the preview pane to show the file, then click Edit
    const editBtn = page.locator('.workspace-edit');
    await editBtn.waitFor({ state: 'visible', timeout: 5000 });
    await editBtn.click();
    await expect(page.locator('.tab-item', { hasText: filename }).first()).toBeVisible();
}

test.describe('Editor Tab UX', () => {

    test('app loads without errors', async ({ page }) => {
        const errors = [];
        page.on('pageerror', (err) => errors.push(err.message));

        await waitForApp(page);

        // No JS errors on initial load
        expect(errors).toEqual([]);

        // Core elements should be present
        await expect(page.locator('.app-shell')).toBeVisible();
    });

    test('clicking a file in workspace tree shows preview', async ({ page }) => {
        await waitForApp(page);
        await clickFileInTree(page, 'README.md');

        // Preview should appear
        const preview = page.locator('.workspace-preview');
        await expect(preview).toBeVisible({ timeout: 5000 });
    });

    test('edit button opens file in editor tab', async ({ page }) => {
        const errors = [];
        page.on('pageerror', (err) => errors.push(err.message));

        await waitForApp(page);
        await openFileInEditor(page, 'README.md');

        // Tab strip should appear with a tab for README.md
        const tabStrip = page.locator('.tab-strip');
        await expect(tabStrip).toBeVisible({ timeout: 5000 });

        const tab = page.locator('.tab-item', { hasText: 'README.md' });
        await expect(tab).toBeVisible();
        await expect(tab).toHaveClass(/active/);

        // Editor pane should be visible
        const editorPane = page.locator('.editor-pane');
        await expect(editorPane).toBeVisible({ timeout: 5000 });

        // No JS errors
        expect(errors).toEqual([]);
    });

    test('can open multiple files as tabs', async ({ page }) => {
        await waitForApp(page);

        // Open first file
        await openFileInEditor(page, 'README.md');
        await expect(page.locator('.tab-item', { hasText: 'README.md' })).toBeVisible();

        // Open second file (must be a text file so Edit button appears)
        await openFileInEditor(page, 'SPEC.md');
        await expect(page.locator('.tab-item', { hasText: 'SPEC.md' })).toBeVisible();

        // Both tabs exist
        const tabs = page.locator('.tab-item');
        await expect(tabs).toHaveCount(2);

        // Second tab should be active
        const specTab = page.locator('.tab-item', { hasText: 'SPEC.md' });
        await expect(specTab).toHaveClass(/active/);
    });

    test('clicking a tab activates it', async ({ page }) => {
        await waitForApp(page);

        await openFileInEditor(page, 'README.md');
        await openFileInEditor(page, 'SPEC.md');

        // Click the README tab
        const readmeTab = page.locator('.tab-item', { hasText: 'README.md' });
        await readmeTab.click();

        await expect(readmeTab).toHaveClass(/active/);

        // SPEC tab should no longer be active
        const specTab = page.locator('.tab-item', { hasText: 'SPEC.md' });
        await expect(specTab).not.toHaveClass(/active/);
    });

    test('close button removes tab', async ({ page }) => {
        await waitForApp(page);
        await openFileInEditor(page, 'README.md');

        const tab = page.locator('.tab-item', { hasText: 'README.md' });
        await expect(tab).toBeVisible();

        // Click the close button within the tab
        const closeBtn = tab.locator('.tab-close');
        await closeBtn.click();

        // Tab should be gone
        await expect(tab).not.toBeVisible();

        // Tab strip should disappear when no tabs remain
        await expect(page.locator('.tab-strip')).not.toBeVisible();
    });

    test('close button does not activate a different tab first', async ({ page }) => {
        await waitForApp(page);

        await openFileInEditor(page, 'README.md');
        await openFileInEditor(page, 'SPEC.md');

        // SPEC.md is active. Close it via its close button.
        const specTab = page.locator('.tab-item', { hasText: 'SPEC.md' });
        const closeBtn = specTab.locator('.tab-close');
        await closeBtn.click();

        // SPEC tab should be gone
        await expect(specTab).not.toBeVisible();

        // README should now be active (fallback)
        const readmeTab = page.locator('.tab-item', { hasText: 'README.md' });
        await expect(readmeTab).toHaveClass(/active/);
    });

    test('context menu shows and has correct items', async ({ page }) => {
        await waitForApp(page);
        await openFileInEditor(page, 'README.md');

        const tab = page.locator('.tab-item', { hasText: 'README.md' });
        await tab.click({ button: 'right' });

        const menu = page.locator('.tab-context-menu');
        await expect(menu).toBeVisible();

        // Should have standard items
        await expect(menu.locator('button', { hasText: 'Close' }).first()).toBeVisible();
        await expect(menu.locator('button', { hasText: 'Close Others' })).toBeVisible();
        await expect(menu.locator('button', { hasText: 'Close All' })).toBeVisible();
        await expect(menu.locator('button', { hasText: 'Pin' })).toBeVisible();

        // Should have popout option
        await expect(menu.locator('button', { hasText: 'Open in Window' })).toBeVisible();

        // README.md should have Preview option
        await expect(menu.locator('button', { hasText: 'Preview' })).toBeVisible();
    });

    test('context menu closes on Escape', async ({ page }) => {
        await waitForApp(page);
        await openFileInEditor(page, 'README.md');

        const tab = page.locator('.tab-item', { hasText: 'README.md' });
        await tab.click({ button: 'right' });
        await expect(page.locator('.tab-context-menu')).toBeVisible();

        await page.keyboard.press('Escape');
        await expect(page.locator('.tab-context-menu')).not.toBeVisible();
    });

    test('pin/unpin via context menu', async ({ page }) => {
        await waitForApp(page);
        await openFileInEditor(page, 'README.md');

        const tab = page.locator('.tab-item', { hasText: 'README.md' });

        // Pin the tab
        await tab.click({ button: 'right' });
        await page.locator('.tab-context-menu button', { hasText: 'Pin' }).click();
        await expect(tab).toHaveClass(/pinned/);

        // Unpin
        await tab.click({ button: 'right' });
        await page.locator('.tab-context-menu button', { hasText: 'Unpin' }).click();
        await expect(tab).not.toHaveClass(/pinned/);
    });

    test('Close Others from context menu', async ({ page }) => {
        await waitForApp(page);
        await openFileInEditor(page, 'README.md');
        await openFileInEditor(page, 'SPEC.md');
        await openFileInEditor(page, 'package.json');

        await expect(page.locator('.tab-item')).toHaveCount(3);

        // Right-click SPEC.md → Close Others
        const specTab = page.locator('.tab-item', { hasText: 'SPEC.md' });
        await specTab.click({ button: 'right' });

        // Handle confirm dialog
        page.once('dialog', (dialog) => dialog.accept());
        await page.locator('.tab-context-menu button', { hasText: 'Close Others' }).click();

        // Only SPEC.md should remain
        await expect(page.locator('.tab-item')).toHaveCount(1);
        await expect(specTab).toBeVisible();
    });

    test('Close All from context menu', async ({ page }) => {
        await waitForApp(page);
        await openFileInEditor(page, 'README.md');
        await openFileInEditor(page, 'SPEC.md');

        const tab = page.locator('.tab-item', { hasText: 'SPEC.md' });
        await tab.click({ button: 'right' });

        page.once('dialog', (dialog) => dialog.accept());
        await page.locator('.tab-context-menu button', { hasText: 'Close All' }).click();

        // No tabs remain
        await expect(page.locator('.tab-strip')).not.toBeVisible();
    });

    test('Open in Window removes tab and opens editor-only popup', async ({ page, context }) => {
        await waitForApp(page);
        await openFileInEditor(page, 'README.md');

        const tab = page.locator('.tab-item', { hasText: 'README.md' });
        await tab.click({ button: 'right' });

        // Listen for new page (popup)
        const popupPromise = context.waitForEvent('page', { timeout: 5000 });
        await page.locator('.tab-context-menu button', { hasText: 'Open in Window' }).click();

        const popup = await popupPromise;
        await popup.waitForLoadState('domcontentloaded');

        // Startup consumes URL parameters; assert the resulting UI instead.
        await expect(popup.locator('.app-shell')).toHaveClass(/popout-mode/);
        await expect(popup.locator('.cm-editor')).toBeVisible();

        // Tab should be removed from the parent window
        await expect(page.locator('.tab-item', { hasText: 'README.md' })).not.toBeVisible();
        await expect(page.locator('.tab-strip')).not.toBeVisible();
    });

    test('popout window is editor-only and shows content', async ({ page, context }) => {
        const errors = [];

        await waitForApp(page);
        await openFileInEditor(page, 'README.md');

        const tab = page.locator('.tab-item', { hasText: 'README.md' });
        await tab.click({ button: 'right' });

        const popupPromise = context.waitForEvent('page', { timeout: 5000 });
        await page.locator('.tab-context-menu button', { hasText: 'Open in Window' }).click();

        const popup = await popupPromise;
        popup.on('pageerror', (err) => errors.push(err.message));
        await popup.waitForLoadState('domcontentloaded');

        // The popup should render editor-only (popout mode)
        await popup.waitForSelector('.app-shell', { timeout: 10_000 });
        await expect(popup.locator('.app-shell')).toHaveClass(/popout-mode/);

        // Tab bar should be hidden in popout mode
        await expect(popup.locator('.tab-strip')).not.toBeVisible();

        // Editor content should be visible
        await expect(popup.locator('.editor-body .cm-editor')).toBeVisible({ timeout: 10_000 });

        // Sidebar and chat should NOT be visible
        await expect(popup.locator('.workspace-sidebar')).not.toBeVisible();
        await expect(popup.locator('.container')).not.toBeAttached();

        // No JS errors in popup
        expect(errors).toEqual([]);
    });

    test('no JS errors throughout full tab lifecycle', async ({ page }) => {
        const errors = [];
        page.on('pageerror', (err) => errors.push(err.message));

        await waitForApp(page);

        // Open → activate → pin → close lifecycle
        await openFileInEditor(page, 'README.md');
        await openFileInEditor(page, 'SPEC.md');

        // Activate first
        await page.locator('.tab-item', { hasText: 'README.md' }).click();
        // Pin it
        await page.locator('.tab-item', { hasText: 'README.md' }).click({ button: 'right' });
        await page.locator('.tab-context-menu button', { hasText: 'Pin' }).click();
        // Close the other
        const specClose = page.locator('.tab-item', { hasText: 'SPEC.md' }).locator('.tab-close');
        await specClose.click();
        // Unpin and close last
        await page.locator('.tab-item', { hasText: 'README.md' }).click({ button: 'right' });
        await page.locator('.tab-context-menu button', { hasText: 'Unpin' }).click();
        const readmeClose = page.locator('.tab-item', { hasText: 'README.md' }).locator('.tab-close');
        await readmeClose.click();

        expect(errors).toEqual([]);
    });

    test('editor tab shows file content', async ({ page }) => {
        await waitForApp(page);
        await openFileInEditor(page, 'README.md');

        // Wait for loading to finish (tab should not say "loading")
        const editorPane = page.locator('.editor-pane');
        await expect(editorPane).toBeVisible({ timeout: 5000 });

        // The CodeMirror editor should be present with content
        const cmContent = page.locator('.cm-content, .cm-editor, .editor-content');
        await expect(cmContent.first()).toBeVisible({ timeout: 5000 });
    });

    test('navigating to /?editor=path directly opens editor', async ({ page }) => {
        const errors = [];
        page.on('pageerror', (err) => errors.push(err.message));

        await page.goto('/?editor=README.md');
        await page.waitForSelector('.app-shell', { timeout: 10_000 });

        // Tab should auto-open
        const tab = page.locator('.tab-item', { hasText: 'README.md' });
        await expect(tab).toBeVisible({ timeout: 10_000 });

        // Editor should be visible
        await expect(page.locator('.editor-pane')).toBeVisible({ timeout: 5000 });

        // URL should be cleaned (no ?editor param)
        await page.waitForFunction(() => !window.location.search.includes('editor='), { timeout: 5000 });

        expect(errors).toEqual([]);
    });
});
