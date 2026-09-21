import {assertQuickActionsReady} from './quick-actions-ready.mjs';
import {assertModelPickerReady} from './model-ready.mjs';
import {assertMessageHoverReady} from './message-hover-ready.mjs';
import {assertWorkspaceReady} from './workspace-ready.mjs';
import {assertQueueReady} from './queue-ready.mjs';
import {readFile} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
import {piclawAssets} from './assets.mjs';
import {piclawReadRoutes} from './piclaw-responses.mjs';
import {piclawChatId} from './piclaw-state.mjs';
import {createRequestDispatcher} from '../routes.mjs';
import {createEventServer} from '../events.mjs';
import {fixtureAvatars} from '../canonical-state.mjs';
export function createPiclawAdapter({runtimeRoot,planSource}){
 const root=resolve(runtimeRoot,'web/static'),assets=piclawAssets({runtimeRoot,planSource});
 let events,dispatcher;const failures=[];
 const mime={'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2'};
 return {name:'piclaw',assets,capabilities:{planSidebar:true,planTool:true},
 async install({page,state,theme}){
  const sid=piclawChatId(state.currentSession);
  events=await createEventServer(['/sse/stream'],{validate:({url})=>{for(const key of url.searchParams.keys())if(key!=='chat_jid')throw new Error('Undeclared SSE query');if(url.searchParams.has('chat_jid')&&url.searchParams.get('chat_jid')!==sid)throw new Error('Wrong SSE chat');}});
  const definitions=piclawReadRoutes(state).map(route=>({...route,respond:async args=>({json:await route.respond(args)})}));
  for(const path of ['/workspace/visibility','/agent/push/presence'])definitions.push({method:'POST',path,respond:()=>({json:{ok:true}})});
  dispatcher=createRequestDispatcher(definitions);
  await page.addInitScript(({state,theme})=>{
   localStorage.setItem('vibes-theme',theme);localStorage.setItem('workspaceOpen',String(state.ui.workspaceOpen));
   localStorage.setItem('piclaw_compose_height',String(state.ui.composeHeight));
   localStorage.setItem('piclaw:plan-sidebar:open',String(state.ui.planOpen));
   localStorage.setItem('piclaw_system_meters_enabled',String(state.ui.metersEnabled));
   localStorage.setItem('piclaw_system_meters_collapsed',String(state.ui.metersCollapsed));
  },{state,theme});
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   try{
    if(url.origin!==events.origin)throw new Error(`External request ${url.origin}`);
    if(url.pathname==='/sse/stream')return route.continue();
    if(Object.hasOwn(fixtureAvatars,url.pathname))return route.fulfill({contentType:'image/svg+xml',body:fixtureAvatars[url.pathname]});
    let file;
    if(url.pathname==='/')file=assets.html;
    else if(url.pathname==='/favicon.ico')file=assets.favicon;
    else if(url.pathname==='/manifest.json')file=assets.manifest;
    else if(url.pathname==='/fixture-plan.js')file=assets.plan;
    else if(url.pathname==='/editor-vendor/codemirror.js')file=assets.editor;
    else if(url.pathname.startsWith('/static/')){
     const relative=decodeURIComponent(url.pathname.slice(8));if(relative.split('/').includes('..'))throw new Error('Asset traversal');file=resolve(root,relative);
    }
    if(file){if(request.method()!=='GET')throw new Error('Invalid asset method');for(const key of url.searchParams.keys())if(!['v','chat_jid'].includes(key))throw new Error('Unexpected asset query');return route.fulfill({body:await readFile(file),contentType:file===assets.plan?'text/javascript':mime[extname(file)]||'application/octet-stream'});}
    return route.fulfill(await dispatcher.dispatch(request));
   }catch(error){failures.push(error.message);return route.fulfill({status:500,json:{error:error.message}});}
  });
  return {url:`${events.origin}/?chat_jid=${encodeURIComponent(sid)}`};
 },
 async ready({page,state}){
  await page.locator('.compose-box textarea').waitFor();
  const dismiss=page.getByRole('button',{name:'Dismiss',exact:true});if(await dismiss.isVisible())await dismiss.click();
  await page.addScriptTag({type:'module',url:new URL('/fixture-plan.js',page.url()).href});
  await page.locator('.plan-sidebar-toggle').waitFor();
  if(state.activity.active){
   await page.waitForFunction(()=>document.readyState==='complete');
   events.emit('/sse/stream','agent_status',{type:state.activity.type==='tool_use'?'tool_call':state.activity.type,title:state.activity.title,tool_call_id:state.activity.turnKey,tool_name:'fixture',chat_jid:piclawChatId(state.currentSession)});
   await page.getByText(state.activity.title,{exact:false}).waitFor({state:'visible'});
  }
  await page.locator('.compose-box textarea').fill(state.compose);
  await page.waitForFunction(expected=>Math.abs(document.querySelector('.compose-box textarea')?.getBoundingClientRect().height-expected)<=1,state.ui.composeHeight).catch(async error=>{const height=(await page.locator('.compose-box textarea').boundingBox())?.height;throw new Error(`${error.message}; Piclaw canonical compose height ${height}, expected ${state.ui.composeHeight}`);});
  if(state.ui.planOpen)await page.waitForFunction(markdown=>[...document.querySelectorAll('.plan-sidebar-editor .cm-line')].map(line=>line.textContent).join('\n')===markdown,state.plan.markdown);
  const expected=state.messages.filter(message=>message.sessionKey===state.currentSession).map(message=>message.id);
  for(const id of expected)await page.locator(`#post-${id}`).waitFor();
  const actual=await page.locator('.timeline .post').evaluateAll(posts=>posts.map(post=>Number(post.id.replace('post-',''))));
  if(JSON.stringify(actual)!==JSON.stringify(expected))throw new Error('Piclaw message order mismatch');
  await assertQueueReady(page,state);
  await assertWorkspaceReady(page,state);
  await assertMessageHoverReady(page,state);
  await assertModelPickerReady(page,state);
  await assertQuickActionsReady(page,state);
  if(state.ui.popup==='sessions'){
   await page.getByRole('button',{name:/^Manage sessions/i}).click();
   await page.locator('.compose-session-popup').waitFor({state:'visible'});
   await page.waitForFunction(ids=>ids.every(id=>document.querySelector('.compose-session-popup')?.textContent.includes(id)),state.sessions.map(session=>piclawChatId(session.key)));
   await page.locator('#compose-session-search').waitFor({state:'visible'});
  }
 },
 assertRequests(){dispatcher?.assertRequests();events?.assertRequests();if(failures.length)throw new Error(failures.join('; '));},
 async dispose(){await events?.dispose();},
 };
}
