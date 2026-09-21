import {assertQuickActionsReady} from './quick-actions-ready.mjs';
import {assertModelPickerReady} from './model-ready.mjs';
import {assertWorkspaceReady} from './workspace-ready.mjs';
import {assertQueueReady} from './queue-ready.mjs';
import {readFile} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
import {tauAssets} from './assets.mjs';
import {tauReadRoutes} from './tau-responses.mjs';
import {tauSessionId,tauStateGaps} from './tau-state.mjs';
import {createRequestDispatcher} from '../routes.mjs';
import {createEventServer} from '../events.mjs';
import {byteLabel} from '../metric-labels.mjs';
import {fixtureAvatars} from '../canonical-state.mjs';

export function createTauAdapter({frontendRoot,sharedStaticRoot}){
 const root=resolve(frontendRoot),shared=resolve(sharedStaticRoot);
 let dispatcher,events;const failures=[];
 const mime={'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2'};
 return {
  name:'tau',assets:tauAssets({frontendRoot:root,sharedStaticRoot:shared}),
  capabilities:{planSidebar:true,planTool:true},
  async install({page,state,theme}){
   dispatcher=createRequestDispatcher(tauReadRoutes(state).map(route=>({...route,respond:async args=>({json:await route.respond(args)})})));
   events=await createEventServer(['/api/events']);
   await page.addInitScript(({state,theme})=>{
    localStorage.setItem('vibes-theme',theme);
    localStorage.setItem('piclaw_compose_height',String(state.ui.composeHeight));
    localStorage.setItem('tau.plan.open',String(state.ui.planOpen));
    localStorage.setItem('workspaceOpen',String(state.ui.workspaceOpen));
    localStorage.setItem('tau.meters.collapsed',String(state.ui.metersCollapsed));
   },{state,theme});
   await page.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    try{
     if(url.origin!==events.origin)throw new Error(`External request ${url.origin}`);
     if(url.pathname==='/api/events')return route.continue();
     if(Object.hasOwn(fixtureAvatars,url.pathname)){
      if(request.method()!=='GET'||[...url.searchParams.keys()].some(key=>key!=='v'))throw new Error('Invalid avatar request');
      return route.fulfill({contentType:'image/svg+xml',body:fixtureAvatars[url.pathname]});
     }
     if(request.method()==='GET'&&url.pathname==='/manifest.json'&&!url.search)return route.fulfill({path:resolve(root,'manifest.json'),contentType:'application/manifest+json'});
     if(request.method()==='GET'&&url.pathname==='/')return route.fulfill({path:resolve(root,'index.html'),contentType:'text/html'});
     if(url.pathname.startsWith('/static/')){
      if(request.method()!=='GET')throw new Error('Invalid static method');
      for(const key of url.searchParams.keys())if(key!=='v')throw new Error('Unexpected asset query');
      const relative=decodeURIComponent(url.pathname.slice(8));
      if(relative.split('/').includes('..'))throw new Error('Asset traversal');
      const file=['extension-ui.js','frontend-sdk.js','widget-bridge.js'].includes(relative)?resolve(shared,relative):resolve(root,relative);
      return route.fulfill({body:await readFile(file),contentType:mime[extname(file)]||'application/octet-stream'});
     }
     return route.fulfill(await dispatcher.dispatch(request));
    }catch(error){failures.push(error.message);return route.fulfill({status:500,json:{error:error.message}});}
   });
   return {url:`${events.origin}/?session=${encodeURIComponent(tauSessionId(state.currentSession))}`};
  },
  async ready({page,state}){
   await page.locator('.compose-box textarea').waitFor();
   const selected=state.sessions.find(session=>session.key===state.currentSession);
   if(!selected)throw new Error('Canonical selected session missing');
   await page.waitForFunction(name=>document.querySelector('[data-testid="session-switcher"]')?.textContent.trim()===`@${name}`,selected.name);
   await page.locator('.compose-box textarea').fill(state.compose);
   await page.waitForFunction(expected=>Math.abs(document.querySelector('.compose-box textarea')?.getBoundingClientRect().height-expected)<=1,state.ui.composeHeight).catch(async error=>{const height=(await page.locator('.compose-box textarea').boundingBox())?.height;throw new Error(`${error.message}; Tau canonical compose height ${height}, expected ${state.ui.composeHeight}`);});
   if(state.messages.length){
    const expected=state.messages.filter(message=>message.sessionKey===state.currentSession);
    for(const message of expected)await page.locator(`#post-${message.id}`).waitFor();
    const actual=await page.locator('.timeline .post').evaluateAll(posts=>posts.map(post=>Number(post.id.replace('post-',''))));
    if(JSON.stringify(actual)!==JSON.stringify(expected.map(message=>message.id)))throw new Error(`Tau message order mismatch: ${JSON.stringify(actual)}`);
   }
   if(state.ui.metersEnabled&&!state.ui.metersCollapsed&&state.metrics.buffer_cache_bytes>0){
    const buffer=page.locator('.system-meters-row.buf .system-meters-value');
    if(page.viewportSize().width>600){await buffer.waitFor();if(await buffer.innerText()!==byteLabel(state.metrics.buffer_cache_bytes))throw new Error('Canonical buffer value mismatch');}
    else await page.locator('.system-meters-compact-summary').filter({hasText:`BUF ${byteLabel(state.metrics.buffer_cache_bytes)}`}).waitFor();
   }
   if(Number.isFinite(state.context.tokens)&&Number.isFinite(state.context.window)){
    const context=page.locator('.compose-context-pie');await context.waitFor();
    if(!(await context.getAttribute('title'))?.includes('Locally estimated'))throw new Error('Tau context estimate is not labelled');
   }
   const gaps=tauStateGaps(state).filter(gap=>!['buffer-cache-metric','token-context-usage'].includes(gap));
   if(gaps.length)throw new Error(`Tau canonical capability gaps: ${gaps.join(', ')}`);
   if(state.ui.planOpen){
    await page.locator('.plan-sidebar-editor .cm-content').waitFor();
    await page.waitForFunction(markdown=>[...document.querySelectorAll('.plan-sidebar-editor .cm-line')].map(line=>line.textContent).join('\n')===markdown,state.plan.markdown);
    if(await page.locator('.plan-sidebar-subtitle').innerText()!==tauSessionId(state.currentSession))throw new Error('Tau Plan session mismatch');
   }
   if(await page.locator('.compose-box textarea').inputValue()!==state.compose)throw new Error('Tau compose draft mismatch');
   await assertQueueReady(page,state);
  await assertWorkspaceReady(page,state);
  await assertModelPickerReady(page,state);
  await assertQuickActionsReady(page,state);
  if(state.ui.popup==='sessions'){
    await page.getByRole('button',{name:/^Manage sessions/i}).click();
    await page.locator('.compose-session-popup').waitFor({state:'visible'});
    await page.waitForFunction(ids=>ids.every(id=>document.querySelector('.compose-session-popup')?.textContent.includes(id)),state.sessions.map(session=>tauSessionId(session.key)));
    await page.locator('#compose-session-search').waitFor({state:'visible'});
   }
  },
  assertRequests(){dispatcher?.assertRequests();events?.assertRequests();if(failures.length)throw new Error(failures.join('; '));},
  async dispose(){await events?.dispose();},
 };
}
