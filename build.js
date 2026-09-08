/**
 * build.js – Bundle the Vibes frontend with Bun.
 *
 * Bundles all JS (app, components, api, preact-htm, katex, marked,
 * codemirror, beautiful-mermaid) into a single ESM file and all CSS
 * (KaTeX + pinned classic layers + Vibes adapters) into one stylesheet under static/dist/.
 *
 * Usage:  bun run build.js
 */

import { resolve, dirname } from "path";
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const staticDir = resolve(__dirname, "src/vibes/static");
const distDir = resolve(staticDir, "dist");

// ── JS bundle ─────────────────────────────────────────────────────────────
const jsResult = await Bun.build({
  entrypoints: [resolve(staticDir, "js/app.js")],
  outdir: distDir,
  format: "esm",
  minify: true,
  sourcemap: "external",
  target: "browser",
});

if (!jsResult.success) {
  console.error("JS build failed:");
  for (const msg of jsResult.logs) console.error(msg);
  process.exit(1);
}

for (const o of jsResult.outputs) {
  const rel = o.path.replace(staticDir + "/", "");
  console.log(`  ${rel}  ${(o.size / 1024).toFixed(1)} KB`);
}

// ── CSS bundle ────────────────────────────────────────────────────────────
// Concatenate all CSS sources then minify with bun's transpiler.
const cssSources = [
  resolve(staticDir, "css/katex.min.css"),
  // Preserve the deployed classic manifest order. Vibes adapters come last.
  ...["base", "shell", "workspace", "editor", "chat", "content", "agent", "overlays", "responsive", "settings"]
    .map(name => resolve(staticDir, `css/classic/${name}.css`)),
  resolve(staticDir, "css/styles.css"),
];

const combined = cssSources
  .map((f) => readFileSync(f, "utf-8").replaceAll('../../common/fonts/', '../common/fonts/'))
  .join("\n");

// Bun doesn't have a CSS-only build API, so we do basic minification:
// collapse whitespace, strip comments, trim lines.
const minified = combined
  .replace(/\/\*[\s\S]*?\*\//g, "")   // strip block comments
  .replace(/\s*\n\s*/g, "\n")          // collapse around newlines
  .replace(/\n+/g, "\n")              // collapse multiple newlines
  .replace(/;\s*}/g, "}")             // drop last semicolon before }
  .replace(/\s*{\s*/g, "{")           // collapse around {
  .replace(/\s*}\s*/g, "}")           // collapse around }
  .replace(/\s*:\s*/g, ":")           // collapse around :
  .replace(/\s*;\s*/g, ";")           // collapse around ;
  .replace(/\s*,\s*/g, ",")           // collapse around ,
  .trim();

mkdirSync(distDir, { recursive: true });
const cssOut = resolve(distDir, "app.css");
writeFileSync(cssOut, minified, "utf-8");
const cssKb = (Buffer.byteLength(minified) / 1024).toFixed(1);
console.log(`  dist/app.css  ${cssKb} KB`);

console.log(`\nBuild complete.`);
