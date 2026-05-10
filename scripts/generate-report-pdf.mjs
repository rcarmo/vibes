#!/usr/bin/env node
/**
 * Generate a PDF test report from Playwright JSON results + screenshots.
 *
 * Usage: node scripts/generate-report-pdf.mjs [--output report.pdf]
 *
 * Uses Playwright's installed Chromium to render HTML → PDF.
 * Falls back to HTML-only output if Chromium is not available.
 */

import { readFileSync, existsSync, writeFileSync, mkdirSync } from 'fs';
import { dirname } from 'path';

const OUTPUT = process.argv.includes('--output')
    ? process.argv[process.argv.indexOf('--output') + 1]
    : 'test-results/vibes-ux-report.pdf';

const RESULTS_PATH = 'test-results/results.json';

if (!existsSync(RESULTS_PATH)) {
    console.error(`Error: ${RESULTS_PATH} not found. Run 'bunx playwright test' first.`);
    process.exit(1);
}

const results = JSON.parse(readFileSync(RESULTS_PATH, 'utf-8'));

// ── Helpers ──────────────────────────────────────────────────────

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function emoji(s) { return s === 'passed' ? '✅' : s === 'failed' ? '❌' : s === 'timedOut' ? '⏱️' : s === 'skipped' ? '⏭️' : '❓'; }
function dur(ms) { return ms < 1000 ? `${ms}ms` : `${(ms/1000).toFixed(1)}s`; }
function b64(path) { try { return `data:image/png;base64,${readFileSync(path).toString('base64')}`; } catch { return ''; } }

// ── Collect tests ────────────────────────────────────────────────

const allTests = [];
function collect(suite, prefix = '') {
    const name = prefix ? `${prefix} › ${suite.title}` : suite.title;
    for (const spec of suite.specs || []) {
        for (const test of spec.tests || []) {
            for (const result of test.results || []) {
                allTests.push({
                    suite: name, title: spec.title,
                    status: result.status, duration: result.duration || 0,
                    error: result.error?.message || '',
                    attachments: result.attachments || [],
                });
            }
        }
    }
    for (const child of suite.suites || []) collect(child, name);
}
for (const s of results.suites || []) collect(s);

const passed = allTests.filter(t => t.status === 'passed').length;
const failed = allTests.filter(t => t.status === 'failed').length;
const total = allTests.length;
const totalDur = allTests.reduce((s, t) => s + t.duration, 0);

// ── Build HTML ───────────────────────────────────────────────────

let html = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:40px;color:#222;font-size:11px}
h1{font-size:22px;margin-bottom:4px}h2{font-size:15px;margin-top:20px;border-bottom:1px solid #ddd;padding-bottom:3px}
.summary{margin:10px 0;font-size:13px}.summary span{margin-right:14px}
.pass{color:#1a7f37}.fail{color:#cf222e}.skip{color:#656d76}
table{width:100%;border-collapse:collapse;margin:6px 0}th,td{text-align:left;padding:3px 6px;border-bottom:1px solid #eee}
th{background:#f6f8fa;font-weight:600}tr.failed{background:#fff0f0}
.error{color:#cf222e;font-size:10px;white-space:pre-wrap;max-width:550px}
.screenshot{max-width:100%;max-height:250px;margin:6px 0;border:1px solid #ddd;border-radius:3px}
.ts{color:#656d76;font-size:10px}
</style></head><body>
<h1>Vibes UX Test Report</h1>
<p class="ts">Generated: ${new Date().toISOString()}</p>
<div class="summary">
<span class="pass">✅ ${passed} passed</span>
<span class="fail">❌ ${failed} failed</span>
<span>${total} total · ${dur(totalDur)}</span>
</div>`;

const bySuite = {};
for (const t of allTests) { (bySuite[t.suite] ??= []).push(t); }

for (const [suite, tests] of Object.entries(bySuite)) {
    const sp = tests.filter(t => t.status === 'passed').length;
    html += `<h2>${esc(suite)} (${sp}/${tests.length})</h2><table><tr><th></th><th>Scenario</th><th>Time</th></tr>`;
    for (const t of tests) {
        const rc = t.status === 'failed' ? ' class="failed"' : '';
        html += `<tr${rc}><td>${emoji(t.status)}</td><td>${esc(t.title)}`;
        if (t.error) html += `<br><span class="error">${esc(t.error.substring(0,250))}</span>`;
        html += `</td><td>${dur(t.duration)}</td></tr>`;
        for (const att of t.attachments.filter(a => a.contentType === 'image/png' && a.path)) {
            const src = b64(att.path);
            if (src) html += `<tr><td></td><td colspan="2"><img class="screenshot" src="${src}"></td></tr>`;
        }
    }
    html += `</table>`;
}
html += `</body></html>`;

// ── Render PDF ───────────────────────────────────────────────────

mkdirSync(dirname(OUTPUT), { recursive: true });
const htmlPath = OUTPUT.replace(/\.pdf$/, '.html');
writeFileSync(htmlPath, html);
console.log(`HTML report: ${htmlPath}`);

try {
    // Try Playwright Chromium
    const { chromium } = await import('playwright');
    const browser = await chromium.launch();
    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: 'load' });
    await page.pdf({
        path: OUTPUT, format: 'A4',
        margin: { top: '16mm', bottom: '16mm', left: '12mm', right: '12mm' },
        printBackground: true,
    });
    await browser.close();
    console.log(`PDF report: ${OUTPUT}`);
} catch (err) {
    console.log(`PDF rendering failed (${err.message}), HTML report available at ${htmlPath}`);
    // Copy HTML as fallback
    writeFileSync(OUTPUT.replace(/\.pdf$/, '.html'), html);
}
