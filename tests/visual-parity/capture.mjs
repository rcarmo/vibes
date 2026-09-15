/** @script Run isolated, deterministic full-app Vibes/Piclaw visual comparisons.
 * bun tests/visual-parity/capture.mjs [--out PATH] [--browsers chromium,webkit]
 * [--scenarios idle,working,sessions,models,quick-actions,attachment] [--viewports desktop,tablet,mobile]
 * [--reference PATH] [--repeat 2]
 */
import { chromium, webkit, expect } from '@playwright/test';
import { PNG } from 'pngjs';
import { compare, sideBySide, overlay, unionRegion, diffOptions } from './images.mjs';
import { mkdir, readFile, writeFile, readdir } from 'node:fs/promises';
import { resolve, dirname, extname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { state, scenarios, viewports } from './state.mjs';
import { apiResponse, events } from './adapters.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const args=process.argv.slice(2); const arg=(name,fallback)=>{const i=args.indexOf('--'+name);return i<0?fallback:args[i+1];};
const output=resolve(arg('out','/workspace/tmp/vibes-visual-diffs'));
const reference=resolve(arg('reference','/opt/piclaw/releases/piclaw-3.1.2-linux-x64-baseline/app/runtime/web/static'));
const browsers=arg('browsers','chromium,webkit').split(',');
const chosenScenarios=arg('scenarios',scenarios.join(',')).split(',');
const chosenViews=arg('viewports',Object.keys(viewports).join(',')).split(',');
const repeats=Number(arg('repeat','2'));
if(![1,2].includes(repeats))throw Error('--repeat must be 1 or 2');
for(const s of chosenScenarios)if(!scenarios.includes(s))throw Error('Unknown scenario '+s);
for(const v of chosenViews)if(!viewports[v])throw Error('Unknown viewport '+v);
await mkdir(output,{recursive:true});
if((await readdir(output)).length)throw Error('Output directory is not empty; use a new directory to retain previous evidence');
const mime={'.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2','.woff':'font/woff','.png':'image/png','.json':'application/json','.html':'text/html'};
const chart=new PNG({width:400,height:120});for(let y=0;y<120;y++)for(let x=0;x<400;x++){const i=(y*400+x)*4;chart.data.set(x>20&&x<380&&y>30&&y<90?[36,87,108,255]:[24,40,50,255],i);}const chartBytes=PNG.sync.write(chart);
function assetPath(app,path){
 if(app==='piclaw' && path.startsWith('/editor-vendor/')) return resolve(reference,'../../extensions/viewers/editor/vendor',path.slice('/editor-vendor/'.length));
 if(path==='/')return app==='vibes'?resolve(root,'src/vibes/static/index.html'):resolve(reference,'classic/index.html');
 if(!path.startsWith('/static/'))return null;
 const base=app==='vibes'?resolve(root,'src/vibes/static'):reference;
 const p=resolve(base,path.slice('/static/'.length));
 return relative(base,p).startsWith('..')?null:p;
}
function freeze({app,now,compose}) {
 const NativeDate=Date;class FixedDate extends NativeDate{constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}}
 window.Date=FixedDate;
 localStorage.clear();sessionStorage.clear();
 const values=app==='piclaw'?{piclaw_theme:'dark',piclaw_system_meters_enabled:'true',piclaw_system_meters_collapsed:'false',workspaceVisible:'false',workspaceOpen:'false',piclaw_workspace_visible:'false',piclaw_compose_height:'80'}:{workspaceOpen:'false',workspaceVisible:'false',vibes_theme:'dark',vibes_system_meters_collapsed:'false',piclaw_compose_height:'80'};
 for(const [k,v]of Object.entries(values))localStorage.setItem(k,v);
 window.__fixtureStreams=[];
 class Stream {
  static CONNECTING=0;static OPEN=1;static CLOSED=2;
  constructor(url){this.url=url;this.readyState=0;this.listeners=new Map();window.__fixtureStreams.push(this);setTimeout(()=>{this.readyState=1;this.onopen?.({});this.emit('connected',{});},30);}
  addEventListener(t,fn){if(!this.listeners.has(t))this.listeners.set(t,new Set());this.listeners.get(t).add(fn);}
  removeEventListener(t,fn){this.listeners.get(t)?.delete(fn);}
  emit(t,data){const event={type:t,data:JSON.stringify(data)};for(const fn of this.listeners.get(t)||[])fn(event);}
  close(){this.readyState=2;}
 }
 window.EventSource=Stream;
 window.__emitFixture=(t,data)=>{for(const stream of window.__fixtureStreams)if(stream.readyState!==2)stream.emit(t,data);};
 // No real sockets or service workers in the isolated fixture context.
 window.WebSocket=class{constructor(){throw Error('Unmocked WebSocket in visual fixture');}};
}
async function capture(browser,app,scenario,view,pass){
 const context=await browser.newContext({viewport:viewports[view],deviceScaleFactor:1,colorScheme:'dark',locale:'en-GB',timezoneId:'UTC',reducedMotion:'reduce',serviceWorkers:'block'});
 const page=await context.newPage();const requests=[],errors=[],unhandled=[];
 page.on('pageerror',e=>errors.push(e.message));
 await context.addInitScript(freeze,{app,now:Date.parse(state.now),compose:state.compose});
 await context.route('**/*',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname;requests.push({method:req.method(),path});
  if(url.hostname!=='fixture.invalid'){unhandled.push({external:req.url()});return route.abort();}
  const file=assetPath(app,path);
  if(file){try{return await route.fulfill({contentType:mime[extname(file)]||'application/octet-stream',body:await readFile(file)});}catch{unhandled.push({asset:path});return route.fulfill({status:404,body:'Missing fixture asset'});}}
  if(path==='/favicon.ico')return route.fulfill({status:204,body:''});
  if(path.startsWith('/fixture/')||path.startsWith('/avatar/')){const color=path.includes('user')?'#9f613f':'#326b82';return route.fulfill({contentType:'image/svg+xml',body:`<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" rx="12" fill="${color}"/></svg>`});}
  if(path==='/media/7'||path==='/media/7/thumbnail')return route.fulfill({contentType:'image/png',body:chartBytes});
  const data=apiResponse(app,path,scenario);
  if(data!==undefined)return route.fulfill({contentType:'application/json',body:JSON.stringify(data),headers:{'Cache-Control':'no-store'}});
  unhandled.push({method:req.method(),path});
  return route.fulfill({contentType:'application/json',body:'{}'});
 });
 const stem=`${browser.browserType().name()}-${view}-${scenario}-${app}${pass?'-repeat':''}`;
 try{
  await page.goto('http://fixture.invalid/',{waitUntil:'domcontentloaded'});
  await expect(page.locator('.compose-box textarea').first()).toBeVisible({timeout:20000});
  await page.evaluate(()=>document.fonts.ready);
  await page.addStyleTag({content:'*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}'});
  // Set presentation options through existing UI where available, not CSS.
  const hide=page.getByRole('button',{name:'Hide workspace',exact:true});if(await hide.count())await hide.first().click();
  await page.locator('.compose-box textarea').first().fill(state.compose);
  await page.locator('.compose-box textarea').first().blur();
  for(const [type,data]of events(app,scenario))await page.evaluate(([t,d])=>window.__emitFixture(t,d),[type,data]);
  // Refresh Vibes' lazy registry through its normal picker (Piclaw loads it on boot).
  if(app==='vibes') {await page.getByTestId('session-switcher').click();await expect(page.getByRole('combobox',{name:'Search sessions'})).toBeFocused();await page.keyboard.press('Escape');await expect(page.getByTestId('session-popup')).toHaveCount(0);await page.getByTestId('session-switcher').blur();}
  if(scenario==='sessions')await page.locator('.compose-session-switcher-btn, [data-testid="session-switcher"]').first().click();
  if(scenario==='models')await page.locator('.compose-model-hint-btn').first().click();
  if(scenario==='quick-actions'){
   await page.waitForTimeout(250);
   await page.locator('#post-101 .post-content').click();
   await page.keyboard.type('m');
   await expect(page.locator('.timeline-quick-actions-input')).toBeVisible();
   await page.locator('.timeline-quick-actions-input').fill('');
  }
  await page.waitForTimeout(500);
  await page.mouse.move(1, 1);
  if(!['sessions','models','quick-actions'].includes(scenario)) await page.evaluate(()=>{document.body.tabIndex=-1;document.body.focus();});
  // Assert shared semantic state rather than accepting any two screenshots.
  await expect(page.locator('#post-101')).toContainText(state.messages[0].text);
  await expect(page.locator('#post-102')).toContainText('Same content, same viewport, different renderers.');
  await expect(page.locator('.compose-box textarea').first()).toHaveValue(state.compose);
  await expect(page.locator('.compose-model-hint-btn').first()).toContainText('fixture-model');
  await expect(page.locator('.system-meters-hud')).toContainText('CPU');
  await expect(page.locator('.system-meters-hud')).toContainText('25%');
  await expect(page.locator('.oobe-panel')).toHaveCount(0);
  if(scenario==='working') {
   await expect(page.locator('.agent-status-panel')).toContainText(state.status);
   await expect(page.locator('.agent-status-panel')).toContainText('Keep the session state identical.');
   await expect(page.locator('.agent-status-panel')).toContainText('The result will include a screenshot.');
   await expect(page.locator('.compose-box')).toContainText(state.queue);
   await expect(page.locator('.compose-send-stack .abort-mode')).toBeVisible();
  }
  if(scenario==='sessions')await expect(page.locator('.compose-session-popup')).toContainText(/research/i);
  if(scenario==='quick-actions')await expect(page.locator('.timeline-quick-actions')).toContainText('/context');
  if(scenario==='models')await expect(page.locator('.compose-model-popup')).toContainText('fixture-model');
  if(scenario==='attachment')await expect(page.locator('#post-103 img[src*="/media/7"]')).toBeVisible();
  if(errors.length || unhandled.length)throw Error('Fixture diagnostics: '+JSON.stringify({errors,unhandled}));
  await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode().catch(()=>{})));await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));});
  const geometry=await page.evaluate(()=>Object.fromEntries(['.compose-box','.timeline','.agent-status-panel','.compose-session-popup','.compose-model-popup','.timeline-quick-actions','.system-meters-hud','.post','#post-103 img','.compose-input-wrapper','.compose-input-main','.compose-box textarea','.compose-footer','.compose-footer-left','.compose-actions','.compose-context-group','.compose-model-hint-btn','.compose-session-switcher-btn','.compose-context-pie','.agent-thinking-title','.agent-thinking-body'].map(selector=>[selector,[...document.querySelectorAll(selector)].map(el=>{const b=el.getBoundingClientRect(),s=getComputedStyle(el);return {x:b.x,y:b.y,width:b.width,height:b.height,font:s.font,fontSize:s.fontSize,color:s.color,background:s.backgroundColor,padding:s.padding,border:s.border,display:s.display};})])));
  await page.screenshot({path:resolve(output,stem+'.png'),animations:'disabled'});
  const text=await page.locator('body').innerText();
  const focus=await page.evaluate(()=>({tag:document.activeElement?.tagName,classes:document.activeElement?.className}));
  const result={focus,stem,app,scenario,view,pass,geometry,errors,unhandled,requests,text};
  await writeFile(resolve(output,stem+'.json'),JSON.stringify(result,null,2));
  return result;
 }catch(error){await page.screenshot({path:resolve(output,stem+'-failed.png')}).catch(()=>{});await writeFile(resolve(output,stem+'-failed.json'),JSON.stringify({error:String(error),errors,requests,unhandled,text:await page.locator('body').innerText().catch(()=>'' )},null,2));throw error;}
 finally{await context.close();}
}
const results=[];let failures=0;const browserVersions={};
for(const name of browsers){const type={chromium,webkit}[name];if(!type)throw Error('Unknown browser');const browser=await type.launch({headless:false});browserVersions[name]=browser.version();try{for(const view of chosenViews)for(const scenario of chosenScenarios){try{
 const captures={};for(let pass=0;pass<repeats;pass++)for(const app of ['piclaw','vibes']){console.log('capture',name,view,scenario,app,pass);captures[app+(pass?'-repeat':'')]=await capture(browser,app,scenario,view,pass);}
 const a=PNG.sync.read(await readFile(resolve(output,captures.piclaw.stem+'.png'))),b=PNG.sync.read(await readFile(resolve(output,captures.vibes.stem+'.png')));
 const diff=compare(a,b),prefix=`${name}-${view}-${scenario}`;await writeFile(resolve(output,prefix+'-diff.png'),PNG.sync.write(diff.diff));
 await writeFile(resolve(output,prefix+'-side-by-side.png'),PNG.sync.write(sideBySide(a,b)));
 await writeFile(resolve(output,prefix+'-overlay.png'),PNG.sync.write(overlay(a,b)));
 const regions={};
 for(const [name,selector]of Object.entries({composer:'.compose-box',status:'.agent-status-panel',meters:'.system-meters-hud',sessions:'.compose-session-popup',models:'.compose-model-popup',quick:'.timeline-quick-actions',timeline:'.timeline'})){
  const region=unionRegion(a,b,selector,[captures.piclaw.geometry,captures.vibes.geometry]);if(!region)continue;
  regions[name]={rect:region.rect,differentPixels:region.count,ratio:region.ratio};
  await writeFile(resolve(output,prefix+'-'+name+'-comparison.png'),PNG.sync.write(sideBySide(region.left,region.right)));
 }
 const stability={};if(repeats===2)for(const app of ['piclaw','vibes']){const first=PNG.sync.read(await readFile(resolve(output,captures[app].stem+'.png'))),second=PNG.sync.read(await readFile(resolve(output,captures[app+'-repeat'].stem+'.png')));stability[app]=compare(first,second).count;}
 results.push({prefix,view,scenario,browser:name,differentPixels:diff.count,ratio:diff.ratio,regions,stability,captures});
 console.log('diff',prefix,(diff.ratio*100).toFixed(2)+'%', 'repeat',JSON.stringify(stability));
 }catch(error){failures++;console.error(name,view,scenario,String(error));}}}finally{await browser.close();}}
const sha=async p=>createHash('sha256').update(await readFile(p)).digest('hex');
const manifest={createdAt:new Date().toISOString(),git:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),reference,
 hashes:{piclawJs:await sha(resolve(reference,'classic/dist/app.bundle.js')),piclawCss:await sha(resolve(reference,'classic/dist/app.bundle.css')),vibesJs:await sha(resolve(root,'src/vibes/static/dist/app.js')),vibesCss:await sha(resolve(root,'src/vibes/static/dist/app.css')),fixture:await sha(resolve(root,'tests/visual-parity/state.mjs'))},
 options:{browsers,chosenScenarios,chosenViews,repeats},browserVersions,
 fixturePolicy:{clock:state.now,dpr:1,theme:'dark',locale:'en-GB',timezone:'UTC',headless:false,retries:0,workers:1,network:'all requests intercepted; external blocked',normalisation:['animation/transition disabled','caret hidden','mouse away from controls','focus reset for closed surfaces'],uncovered:['light theme','workspace/editor/terminal panes','permission dialogs','expanded statuses','OS-specific fonts','real-agent execution']},
 sourceHashes:{state:await sha(resolve(root,'tests/visual-parity/state.mjs')),adapters:await sha(resolve(root,'tests/visual-parity/adapters.mjs')),capture:await sha(resolve(root,'tests/visual-parity/capture.mjs')),images:await sha(resolve(root,'tests/visual-parity/images.mjs')),editorVendor:await sha(resolve(reference,'../../extensions/viewers/editor/vendor/codemirror.js'))},pixelmatch:diffOptions,failures,results,unstable:results.filter(r=>Object.values(r.stability).some(n=>n>0)).map(r=>r.prefix)};
await writeFile(resolve(output,'manifest.json'),JSON.stringify(manifest,null,2));
const html=`<!doctype html><meta charset="utf-8"><title>Vibes / Piclaw visual diff</title><style>body{font:15px system-ui;background:#182028;color:#eee;margin:24px}img{max-width:100%;border:1px solid #64748b}section{margin:32px 0}a{color:#7dd3fc}summary{cursor:pointer}code{color:#ddd}</style><h1>Piclaw (left) / Vibes (right)</h1><p>Same fixture. No live API calls. Frozen time; animation/caret disabled. Pixelmatch threshold 0.1 excludes antialiasing. Differences are evidence, not an acceptance score.</p>${results.map(r=>`<section><h2>${r.prefix}: ${(r.ratio*100).toFixed(2)}% pixels differ</h2><p>Repeat changed pixels: ${JSON.stringify(r.stability)}. <a href="${r.prefix}-diff.png">Pixel diff</a> · <a href="${r.prefix}-overlay.png">50% overlay</a> · ${Object.entries(r.regions).map(([name,data])=>`<a href="${r.prefix}-${name}-comparison.png">${name}: ${(data.ratio*100).toFixed(1)}%</a>`).join(' · ')}</p><img loading="lazy" src="${r.prefix}-side-by-side.png"><details><summary>Diff</summary><img loading="lazy" src="${r.prefix}-diff.png"></details></section>`).join('')}<p>See manifest.json for asset hashes, request logs, geometry and fixture diagnostics. Failures: ${failures}.</p>`;
await writeFile(resolve(output,'index.html'),html);
console.log('Report:',resolve(output,'index.html'));if(failures||manifest.unstable.length)process.exitCode=1;
