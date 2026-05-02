#!/usr/bin/env node
/**
 * Generate a PDF test report from Playwright JSON results + screenshots.
 *
 * Usage: node scripts/generate-report-pdf.mjs [--output report.pdf]
 *
 * Reads:
 *   test-results/results.json   — Playwright JSON reporter output
 *   test-results/**/*.png       — Screenshots captured during tests
 *
 * Produces:
 *   A self-contained PDF with pass/fail status, durations, and inline screenshots.
 *
 * Requires Playwright (uses its Chromium to render HTML → PDF).
 */

import { chromium } from 'playwright';
import { readFileSync, existsSync, readdirSync, statSync, writeFileSync } from 'fs';
import { join, basename, resolve } from 'path';

const OUTPUT = process.argv.includes('--output')
    ? process.argv[process.argv.indexOf('--output') + 1]
    : 'test-results/vibes-ux-report.pdf';

const RESULTS_PATH = 'test-results/results.json';

// ── Load results ─────────────────────────────────────────────────

if (!existsSync(RESULTS_PATH)) {
    console.error(`Error: ${RESULTS_PATH} not found. Run 'bunx playwright test' first.`);
    process.exit(1);
}

const results = JSON.parse(readFileSync(RESULTS_PATH, 'utf-8'));

// ── Collect screenshots ──────────────────────────────────────────

function findScreenshots(dir) {
    const shots = {};
    if (!existsSync(dir)) return shots;
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) {
            Object.assign(shots, findScreenshots(full));
        } else if (entry.name.endsWith('.png')) {
            // Map by parent folder name (test name slug)
            const key = basename(join(full, '..'));
            if (!shots[key]) shots[key] = [];
            shots[key].push(full);
        }
    }
    return shots;
}

const screenshots = findScreenshots('test-results');

// ── Build HTML ───────────────────────────────────────────────────

function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function statusEmoji(status) {
    switch (status) {
        case 'passed': return '✅';
        case 'failed': return '❌';
        case 'timedOut': return '⏱️';
        case 'skipped': return '⏭️';
        default: return '❓';
    }
}

function formatDuration(ms) {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
}

function inlineImage(path) {
    try {
        const data = readFileSync(path);
        return `data:image/png;base64,${data.toString('base64')}`;
    } catch {
        return '';
    }
}

const suites = results.suites || [];
const allTests = [];

function collectTests(suite, prefix = '') {
    const name = prefix ? `${prefix} > ${suite.title}` : suite.title;
    for (const spec of suite.specs || []) {
        for (const test of spec.tests || []) {
            for (const result of test.results || []) {
                allTests.push({
                    suite: name,
                    title: spec.title,
                    status: result.status,
                    duration: result.duration || 0,
                    error: result.error?.message || '',
                    attachments: result.attachments || [],
                });
            }
        }
    }
    for (const child of suite.suites || []) {
        collectTests(child, name);
    }
}

for (const suite of suites) {
    collectTests(suite);
}

const passed = allTests.filter(t => t.status === 'passed').length;
const failed = allTests.filter(t => t.status === 'failed').length;
const skipped = allTests.filter(t => t.status === 'skipped').length;
const total = allTests.length;
const totalDuration = allTests.reduce((sum, t) => sum + t.duration, 0);

let html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; color: #222; font-size: 11px; }
  h1 { font-size: 22px; margin-bottom: 4px; }
  h2 { font-size: 16px; margin-top: 24px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
  .summary { margin: 12px 0; font-size: 13px; }
  .summary span { margin-right: 16px; }
  .pass { color: #1a7f37; }
  .fail { color: #cf222e; }
  .skip { color: #656d76; }
  table { width: 100%; border-collapse: collapse; margin: 8px 0; }
  th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid #eee; }
  th { background: #f6f8fa; font-weight: 600; }
  tr.failed { background: #fff0f0; }
  .error { color: #cf222e; font-size: 10px; white-space: pre-wrap; max-width: 600px; }
  .screenshot { max-width: 100%; max-height: 300px; margin: 8px 0; border: 1px solid #ddd; border-radius: 4px; }
  .screenshot-label { font-size: 10px; color: #656d76; }
  .timestamp { color: #656d76; font-size: 10px; }
  .page-break { page-break-before: always; }
</style>
</head>
<body>
<h1>Vibes UX Test Report</h1>
<p class="timestamp">Generated: ${new Date().toISOString()}</p>
<div class="summary">
  <span class="pass">✅ ${passed} passed</span>
  <span class="fail">❌ ${failed} failed</span>
  <span class="skip">⏭️ ${skipped} skipped</span>
  <span>${total} total · ${formatDuration(totalDuration)}</span>
</div>
`;

// Group by suite
const bySuite = {};
for (const t of allTests) {
    if (!bySuite[t.suite]) bySuite[t.suite] = [];
    bySuite[t.suite].push(t);
}

for (const [suite, tests] of Object.entries(bySuite)) {
    const suitePassed = tests.filter(t => t.status === 'passed').length;
    const suiteTotal = tests.length;
    html += `<h2>${escapeHtml(suite)} (${suitePassed}/${suiteTotal})</h2>\n`;
    html += `<table><tr><th>Status</th><th>Scenario</th><th>Duration</th></tr>\n`;
    for (const t of tests) {
        const rowClass = t.status === 'failed' ? ' class="failed"' : '';
        html += `<tr${rowClass}><td>${statusEmoji(t.status)}</td><td>${escapeHtml(t.title)}`;
        if (t.error) {
            html += `<br><span class="error">${escapeHtml(t.error.substring(0, 300))}</span>`;
        }
        html += `</td><td>${formatDuration(t.duration)}</td></tr>\n`;

        // Inline screenshot attachments
        const screenshotAttachments = t.attachments.filter(a => a.contentType === 'image/png' && a.path);
        for (const att of screenshotAttachments) {
            const src = inlineImage(att.path);
            if (src) {
                html += `<tr><td></td><td colspan="2"><span class="screenshot-label">${escapeHtml(att.name || 'screenshot')}</span><br><img class="screenshot" src="${src}"></td></tr>\n`;
            }
        }
    }
    html += `</table>\n`;
}

html += `</body></html>`;

// ── Render to PDF ────────────────────────────────────────────────

console.log(`Rendering PDF (${total} tests, ${Object.keys(screenshots).length} screenshot dirs)...`);

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setContent(html, { waitUntil: 'networkidle' });
await page.pdf({
    path: OUTPUT,
    format: 'A4',
    margin: { top: '20mm', bottom: '20mm', left: '15mm', right: '15mm' },
    printBackground: true,
});
await browser.close();

console.log(`Report written to ${OUTPUT}`);
