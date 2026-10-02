// Local diagnostic: launches only our isolated fixture and a clean headless Edge.
import {chromium, expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const python=process.env.VIBES_TEST_PYTHON;
if(!python || !process.env.COPILOT_CLI_PATH)throw Error('Explicit test Python and runtime required');
const proc=Bun.spawn([python,fileURLToPath(new URL('./ffi_web_smoke.py',import.meta.url))],{stdin:'pipe',stdout:'pipe',stderr:'pipe'});
const outDir=process.env.VIBES_TEST_OUTPUT;if(!outDir)throw Error('Explicit evidence directory required');mkdirSync(outDir,{recursive:true});
const stderrPromise=new Response(proc.stderr).text();let browser;
const reader=proc.stdout.getReader();const decoder=new TextDecoder();let buffer='';
try{
 const deadline=Date.now()+30000;let port;
 while(!port&&Date.now()<deadline){const v=await Promise.race([reader.read(),new Promise((_,reject)=>setTimeout(()=>reject(Error('fixture timeout')),30000))]);if(v.done)throw Error('Fixture stopped');buffer+=decoder.decode(v.value);for(const line of buffer.split('\n')){try{const j=JSON.parse(line);if(j.port)port=j.port;}catch{}}}
 if(!port)throw Error('No fixture port');
 const url=`http://127.0.0.1:${port}`;const health=await(await fetch(url+'/health')).json();if(!health.agent?.ready||health.agent.transport!=='ffi')throw Error('FFI not ready');
 browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1280,height:800}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url,{waitUntil:'networkidle'});await page.screenshot({path:outDir+'/desktop.png'});
 const desktop={title:await page.title(),bodyTextLength:(await page.locator('body').innerText()).length};
 await page.request.post(url+'/fixture/request');
 await expect(page.locator('[data-testid="agent-freeform-answer"]')).toBeVisible();
 const pending=(await(await fetch(url+'/agents/status?session_id=default')).json()).pending_requests[0];
 await page.reload({waitUntil:'networkidle'});
 await expect(page.locator('[data-testid="agent-freeform-answer"]')).toBeVisible();
 await page.locator('[data-testid="agent-freeform-answer"]').fill('Browser synthetic answer');
 await page.getByRole('button',{name:'Submit answer'}).click();
 await expect(page.locator('.agent-request-modal')).toHaveCount(0);
 const replay=await page.request.post(url+'/agent/respond',{data:{request_id:pending.request_id,outcome:'freeform',answer:'replay'}});
 if(replay.status()!==409)throw Error('Stale browser response accepted');
 await page.request.post(url+'/fixture/request?timeout=1');
 await expect(page.locator('[data-testid="agent-freeform-answer"]')).toBeVisible();
 await expect(page.locator('.agent-request-modal')).toHaveCount(0,{timeout:10000});
 await page.setViewportSize({width:390,height:844});await page.reload({waitUntil:'networkidle'});await page.screenshot({path:outDir+'/mobile.png'});
 const terminal=await(await fetch(url+'/terminal/session')).json();if(terminal.enabled!==false)throw Error('Terminal should be disabled');
 const models=await(await fetch(url+'/agent/models')).json();
 writeFileSync(outDir+'/web-smoke.json',JSON.stringify({at:new Date().toISOString(),health,desktop,terminal,models,pageErrors:errors,passed:errors.length===0,modelCalls:0,syntheticRequestUi:{reloadRecovered:true,freeformSubmitted:true,replayRejected:true,timeoutDismissed:true},realBrowser:'clean headless Edge; mobile viewport, not physical phone'},null,2));if(errors.length)throw Error(errors.join('\n'));
 console.log('FFI web health + desktop/mobile viewport boot passed');
}finally{await browser?.close();proc.stdin.write('stop\n');await proc.stdin.end();try{await Promise.race([proc.exited,new Promise((_,reject)=>setTimeout(()=>reject(Error('cleanup timeout')),15000))]);}catch{proc.kill();}writeFileSync(outDir+'/web-stderr.log',await stderrPromise);}
