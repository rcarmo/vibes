import {chromium,webkit} from 'playwright';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {launchHeaded} from './capture.mjs';
import {compareCase} from './compare-case.mjs';
import {createRequestDispatcher} from './routes.mjs';
const root=await mkdtemp(join(tmpdir(),'canonical-harness-smoke-'));
const output=process.env.UI_PARITY_SMOKE_OUT||'/workspace/tmp/ui-parity-harness-smoke';
try{
 const asset=join(root,'index.html');
 const html='<!doctype html><html><head><meta charset="utf-8"><link rel="icon" href="data:,"></head><body><h1>Known fixture</h1><p id="state">Stable state</p></body></html>';
 await writeFile(asset,html);
 for(const engine of [chromium,webkit]){
  const browser=await launchHeaded(engine);
  try{
   const factory=name=>async()=>{
    const dispatcher=createRequestDispatcher([{method:'GET',path:'/',respond:()=>({contentType:'text/html',body:html})}]);
    return{name,assets:{html:asset},install:async({page})=>{
     await page.route('**/*',async route=>{try{await route.fulfill(await dispatcher.dispatch(route.request()));}catch{await route.abort();}});
     return{url:'http://fixture.local/'};
    },ready:async({page})=>{await page.getByRole('heading',{name:'Known fixture',exact:true}).waitFor();if(await page.locator('#state').innerText()!=='Stable state')throw new Error('Wrong state');},assertRequests:()=>dispatcher.assertRequests()};
   };
   const result=await compareCase({browser,adapterFactories:{reference:factory('reference'),candidate:factory('candidate')},state:{},viewport:{width:390,height:844},theme:'light',outDir:join(output,engine.name())});
   if(!result.passed)throw new Error(`${engine.name()} repeatability failure`);
   console.log(`${engine.name()}: headed fresh-context repeats and exact comparison passed`);
  }finally{await browser.close();}
 }
}finally{await rm(root,{recursive:true,force:true});}
