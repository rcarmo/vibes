/**
 * build.js – Bundle the Vibes frontend with Bun.
 *
 * Bundles app.js and its component/API imports into a single ESM file
 * under static/dist/. Vendor libraries (preact-htm, katex, codemirror,
 * beautiful-mermaid) are kept as external imports so the browser loads
 * them from the existing vendor/ directory.
 *
 * Usage:  bun run build.js
 */

import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const staticDir = resolve(__dirname, "src/vibes/static");
const entrypoint = resolve(staticDir, "js/app.js");

const result = await Bun.build({
  entrypoints: [entrypoint],
  outdir: resolve(staticDir, "dist"),
  format: "esm",
  minify: true,
  sourcemap: "external",
  target: "browser",
  external: [
    // Keep vendor libraries external — they're loaded as separate <script>
    // tags or are already self-contained bundles.
    "./vendor/preact-htm.js",
    "../vendor/preact-htm.js",
    "./vendor/katex.min.js",
    "../vendor/katex.min.js",
    "./vendor/codemirror.js",
    "../vendor/codemirror.js",
    "./vendor/beautiful-mermaid.js",
    "../vendor/beautiful-mermaid.js",
  ],
});

if (!result.success) {
  console.error("Build failed:");
  for (const msg of result.logs) {
    console.error(msg);
  }
  process.exit(1);
}

for (const output of result.outputs) {
  const rel = output.path.replace(staticDir + "/", "");
  const kb = (output.size / 1024).toFixed(1);
  console.log(`  ${rel}  ${kb} KB`);
}

console.log(`\nBundled ${result.outputs.length} output(s) successfully.`);
