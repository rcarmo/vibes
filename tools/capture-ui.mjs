#!/usr/bin/env bun
/** Capture desktop/mobile timeline and editor screenshots from a running Vibes server. */
import { parseArgs } from 'node:util';
import { mkdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { chromium, firefox, webkit } from '@playwright/test';

const { values } = parseArgs({ options: {
    url: { type: 'string', default: 'http://127.0.0.1:8765/' },
    output: { type: 'string', default: 'screenshots' },
    file: { type: 'string', default: 'README.md' },
    browser: { type: 'string', default: 'chromium' },
    headed: { type: 'boolean', default: false },
    help: { type: 'boolean', short: 'h' },
} });

if (values.help) {
    console.log('Usage: bun tools/capture-ui.mjs [--url URL] [--output DIR] [--file WORKSPACE_PATH] [--browser chromium|firefox|webkit] [--headed]');
    console.log('Requires a running Vibes server and installed Playwright browser. Output files are overwritten.');
    process.exit(0);
}
const engines = { chromium, firefox, webkit };
if (!Object.hasOwn(engines, values.browser)) throw new Error('Unsupported browser');
const base = new URL(values.url);
if (!['http:', 'https:'].includes(base.protocol)) throw new Error('URL must use HTTP or HTTPS');
if (!values.file.trim()) throw new Error('--file must be a workspace file path');
const output = resolve(values.output);
await mkdir(output, { recursive: true });
const browser = await engines[values.browser].launch({ headless: !values.headed });
try {
    for (const [name, viewport, mobile] of [
        ['desktop', { width: 1440, height: 1000 }, false],
        ['mobile', { width: 390, height: 844 }, true],
    ]) {
        // Firefox does not implement Playwright's isMobile emulation.
        const context = await browser.newContext({ viewport, hasTouch: mobile,
            ...(values.browser === 'firefox' ? {} : { isMobile: mobile }) });
        try {
            const page = await context.newPage();
            for (const view of ['timeline', 'editor']) {
                const url = new URL(base);
                for (const key of ['editor', 'popout', 'editor_popout']) url.searchParams.delete(key);
                if (view === 'editor') url.searchParams.set('editor', values.file);
                const response = await page.goto(url.href, { waitUntil: 'domcontentloaded' });
                if (!response?.ok()) throw new Error(`Navigation failed: HTTP ${response?.status()}`);
                await page.locator(view === 'editor' ? '.cm-editor' : '.app-shell').waitFor({ state: 'visible' });
                await page.evaluate(() => document.fonts.ready);
                const path = join(output, `${values.browser}-${name}-${view}.png`);
                await page.screenshot({ path, fullPage: true });
                console.log(path);
            }
        } finally { await context.close(); }
    }
} finally { await browser.close(); }
