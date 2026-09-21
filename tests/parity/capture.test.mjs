import {test,expect} from 'bun:test';
import {mkdtemp,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {captureCase,launchHeaded} from './capture.mjs';

async function fixture(run){
 const root=await mkdtemp(join(tmpdir(),'capture-contract-'));
 try{
  const asset=join(root,'app.js');await writeFile(asset,'fixture');
  const listeners={};let closed=false,checks=0;
  const page={mouse:{move:async()=>{}},on:(event,fn)=>listeners[event]=fn,clock:{setFixedTime:async()=>{}},goto:async()=>{},bringToFront:async()=>{},waitForTimeout:async()=>{},evaluate:async()=>{},screenshot:async()=>{}};
  const context={newPage:async()=>page,close:async()=>{closed=true;}};
  const browser={newContext:async options=>{expect(options.deviceScaleFactor).toBe(1);return context;}};
  const adapter={name:'fixture',assets:{app:asset},install:async()=>({url:'http://fixture/'}),ready:async()=>{},assertRequests:async()=>{checks++;}};
  await run({root,page,listeners,adapter,browser,isClosed:()=>closed,checks:()=>checks});
 }finally{await rm(root,{recursive:true,force:true});}
}
const args=f=>({browser:f.browser,adapter:f.adapter,state:{},viewport:{width:390,height:844},theme:'light',outDir:join(f.root,'result'),repeat:1});
test('capture checks requests before and after screenshot and closes context',async()=>fixture(async f=>{
 expect((await captureCase(args(f))).passed).toBe(true);expect(f.checks()).toBe(2);expect(f.isClosed()).toBe(true);
}));
test('late browser error is retained and cannot pass',async()=>fixture(async f=>{
 f.page.screenshot=async()=>f.listeners.pageerror(new Error('late render failure'));
 await expect(captureCase(args(f))).rejects.toThrow('Late browser failure');
 const report=JSON.parse(await readFile(join(f.root,'result/capture.json'),'utf8'));
 expect(report.passed).toBe(false);expect(report.errors).toContain('late render failure');expect(f.isClosed()).toBe(true);
}));
test('unknown native route rejects capture with diagnostics',async()=>fixture(async f=>{
 f.adapter.assertRequests=async()=>{throw new Error('Unknown route /unexpected');};
 await expect(captureCase(args(f))).rejects.toThrow('Unknown route');
 expect(JSON.parse(await readFile(join(f.root,'result/capture.json'),'utf8')).failure).toContain('/unexpected');
}));
test('headed launcher rejects silent headless fallback',async()=>{
 await expect(launchHeaded({launch:async()=>{}},{headless:true})).rejects.toThrow('headed');
});
test('all cleanup runs and cleanup failure cannot retain a passing report',async()=>fixture(async f=>{
 let installedDisposed=false,adapterDisposed=false;
 f.browser.newContext=async()=>({newPage:async()=>f.page,close:async()=>{throw new Error('context close failed');}});
 f.adapter.install=async()=>({url:'http://fixture/',dispose:async()=>{installedDisposed=true;throw new Error('stream close failed');}});
 f.adapter.dispose=async()=>{adapterDisposed=true;};
 await expect(captureCase(args(f))).rejects.toThrow('Capture cleanup failed');
 const report=JSON.parse(await readFile(join(f.root,'result/capture.json'),'utf8'));
 expect(report.passed).toBe(false);expect(report.cleanupFailures).toHaveLength(2);
 expect(installedDisposed).toBe(true);expect(adapterDisposed).toBe(true);
}));
