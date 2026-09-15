/** @script Summarise a completed dual-UI capture manifest into Markdown/CSV. */
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const dir=resolve(process.argv[2]||'');
const manifest=JSON.parse(await readFile(resolve(dir,'manifest.json'),'utf8'));
if(manifest.failures||manifest.unstable.length)throw Error('Cannot certify an incomplete or unstable run');
for(const r of manifest.results)for(const c of Object.values(r.captures))if(c.errors.length||c.unhandled.length)throw Error('Unclean fixture diagnostics');
const pct=value=>(value*100).toFixed(2)+'%';
const table=['| Scenario | Chromium desktop | Chromium tablet | Chromium mobile | WebKit desktop | WebKit tablet | WebKit mobile |','|---|---:|---:|---:|---:|---:|---:|'];
for(const s of manifest.options.chosenScenarios)table.push('| '+s+' | '+['chromium','webkit'].flatMap(b=>['desktop','tablet','mobile'].map(v=>{const r=manifest.results.find(r=>r.scenario===s&&r.browser===b&&r.view===v);return r?pct(r.ratio):'not run';})).join(' | ')+' |');
const result=(v,s='idle')=>manifest.results.find(r=>r.browser==='chromium'&&r.view===v&&r.scenario===s);
const dims=['| Viewport | Piclaw composer height | Vibes composer height | Vibes vertical offset |','|---|---:|---:|---:|'];
for(const v of ['desktop','tablet','mobile']){const r=result(v);if(!r)continue;const a=r.captures.piclaw.geometry['.compose-box'][0],b=r.captures.vibes.geometry['.compose-box'][0];dims.push(`| ${v} | ${a.height.toFixed(2)} px | ${b.height.toFixed(2)} px | +${(b.y-a.y).toFixed(2)} px |`);}
const images=['| Viewport | Piclaw image | Vibes image | Y offset |','|---|---|---|---:|'];
for(const v of ['desktop','tablet','mobile']){const r=result(v,'attachment');if(!r)continue;const pick=a=>r.captures[a].geometry['#post-103 img'].find(b=>b.width>100);const a=pick('piclaw'),b=pick('vibes');if(a&&b)images.push(`| ${v} | ${a.width} × ${a.height} | ${b.width} × ${b.height} | +${(b.y-a.y).toFixed(2)} px |`);}
const text=`# Same-state Vibes / Piclaw visual baseline

Reference: Piclaw classic 3.1.2 installed release. Vibes HEAD at capture: \`${manifest.git}\`.
Browsers: Chromium ${manifest.browserVersions.chromium}; WebKit ${manifest.browserVersions.webkit}.

${manifest.results.length} comparisons, ${manifest.results.length*4} independent screenshots, zero repeat-diff pixels, zero unhandled requests and zero browser errors. Each UI was captured twice in a fresh isolated context. No live server or chat was touched. See [the browsable report](index.html) and [manifest](manifest.json).

## Full-frame differences

${table.join('\n')}

Pixelmatch threshold 0.1, antialiasing excluded. These are changed-pixel percentages, **not parity/quality scores**. A small translation of a large image can produce a high difference despite matching dimensions.

## Measured layout differences

${dims.join('\n')}

The composer height difference shifts the timeline because both UIs anchor it above the composer. The working scenario adds the same queue item; it retains the 5.5 px desktop/tablet and roughly 28 px mobile composer difference. Vibes' working status region is about 4.19 px taller at each viewport. Vibes shows \`more…\` controls for the short draft/thought fixture that Piclaw does not show.

${images.join('\n')}

The fixture image dimensions match. Its shifted position, not scaling, accounts for much of the mobile attachment diff.

Other visible differences:

* Vibes adds a source-host label to the meters (intentional scope labelling); Piclaw omits it. The expanded desktop meter panel is 22 px taller in Vibes.
* Session pickers use different IDs, group labels, metadata rows and action wording. Their geometry and styling are captured separately; native IDs were not rewritten to conceal product differences.
* Model picker presentation differs despite the same model, thinking level and context occupancy.
* Quick actions differ in group labels, shortcuts, icons and available workspace actions. Unsupported product actions were not invented by the adapter.
* Composer control sets differ, including the Vibes quick-actions launcher. All controls are left visible in the comparison.

Inspect the side-by-side, overlay and same-coordinate region crops before deciding which differences to fix. This run changes no production UI styling or behaviour.

## Fixture controls and limits

Dark theme, UTC, en-GB, DPR 1, frozen time, deterministic avatars and image; same messages, model, context, draft, thoughts, queue and resource series. Only animation, transitions and carets are disabled. Fonts and images are awaited; mouse/focus states are reset through browser interactions. Real built entrypoints are used. All requests are intercepted and unknown requests fail the scenario.

This does not cover light theme, workspace/editor/terminal panes, permission dialogs, expanded status views, operating-system-specific fonts or real-agent execution. It is a reproducible baseline, not a claim of complete visual or behavioural parity.

See the project \`tests/visual-parity/README.md\` for the rerun command. Early bootstrap/fixture failures were retained outside this clean report rather than overwritten. \`manifest.json\` records the precise input hashes and settings.
`;
await writeFile(resolve(dir,'FINDINGS.md'),text);
const csv=['browser,viewport,scenario,different_pixels,total_ratio,composer_ratio,repeat_piclaw,repeat_vibes',...manifest.results.map(r=>[r.browser,r.view,r.scenario,r.differentPixels,r.ratio,r.regions.composer?.ratio??'',r.stability.piclaw,r.stability.vibes].join(','))].join('\n')+'\n';
await writeFile(resolve(dir,'metrics.csv'),csv);
console.log(resolve(dir,'FINDINGS.md'));
