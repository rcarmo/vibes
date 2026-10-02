// Native runtime -> actual Vibes send/status/preview routes -> real browser SSE.
import {chromium,expect} from '@playwright/test';
import {fileURLToPath} from 'node:url';
const python=process.env.VIBES_TEST_PYTHON, runtime=process.env.COPILOT_CLI_PATH;
if(!python||!runtime)throw Error('Explicit test Python/runtime required');
const proc=Bun.spawn([python,fileURLToPath(new URL('./ffi_stream_web_fixture.py',import.meta.url))],{stdin:'pipe',stdout:'pipe',stderr:'pipe'});
const error=new Response(proc.stderr).text();let browser;
try{
 const reader=proc.stdout.getReader();let buffer='',fixture;const decoder=new TextDecoder();
 while(!fixture){const v=await Promise.race([reader.read(),new Promise((_,reject)=>setTimeout(()=>reject(Error('fixture startup timeout')),25000))]);if(v.done)throw Error('Fixture stopped');buffer+=decoder.decode(v.value);for(const line of buffer.split('\n'))try{const j=JSON.parse(line);if(j.port)fixture=j;}catch{}}
 const url=`http://127.0.0.1:${fixture.port}`;
 browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  const Native=window.EventSource;window.actualDraftEvents=[];
  window.EventSource=class extends Native{constructor(url,options){super(url,options);this.addEventListener('agent_draft',e=>window.actualDraftEvents.push(JSON.parse(e.data)));}};
 });
 await page.goto(url,{waitUntil:'networkidle'});
 await expect.poll(async()=>(await (await page.request.get(url+'/agents/status?session_id=default')).json()).busy,{timeout:20000}).toBe(false);
 const sent=await page.request.post(url+'/agent/default/message',{data:{content:'Synthetic streamed reply',session_id:'default',media_ids:[]}});
 expect(sent.status()).toBe(201);
 const panel=page.locator('[data-panel-key="draft"]'), body=panel.locator('.agent-thinking-body');
 let full='';
 for(let i=0;i<fixture.chunks.length;i++){
  if(i)await page.request.post(url+'/fixture/step');
  full+=fixture.chunks[i];
  if(i<5){
   await expect(body).toHaveText(full.trim());
   const packet=await page.evaluate(()=>window.actualDraftEvents.at(-1));
   expect(packet.mode).toBe('replace');expect(packet.text).toBe(full);
  }
  else await expect(body).toContainText(fixture.chunks[i].trim());
  // Exercise status polling while the stream is waiting (no synthetic EventSource).
  if(i===3){await page.waitForTimeout(5500);await expect(body).toHaveText(full.trim());}
  if(i===15){await panel.getByTitle('Show more Draft',{exact:true}).click();await expect(panel).toHaveAttribute('data-expanded','true');await expect(body).toContainText('A real stream must accumulate.');}
 }
 await expect(body).toContainText('Expanded words remain together.');
 expect((await body.innerText()).match(/Expanded words remain together\./g)).toHaveLength(1);
 await page.request.post(url+'/fixture/step');
 await expect(panel).toHaveCount(0);
 await expect(page.locator('.post-content').filter({hasText:'A real stream must accumulate.'})).toBeVisible();
 if(errors.length)throw Error(errors.join('\n'));
 console.log(JSON.stringify({passed:true,path:'real FFI -> routes -> SSE -> Edge',chunks:fixture.chunks.length,collapsedAccumulates:true,pollingPreservesDraft:true,expandedAccumulates:true,finalMessage:true,pageErrors:errors,externalModelCalls:0}));
}finally{
 await browser?.close();proc.stdin.write('stop\n');await proc.stdin.end();
 try{await Promise.race([proc.exited,new Promise((_,reject)=>setTimeout(()=>reject(Error('cleanup timeout')),15000))]);}catch{proc.kill();}
 const stderr=await error;if(stderr.trim())console.error(stderr);
}
