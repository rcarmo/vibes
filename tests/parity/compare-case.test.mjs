import {test,expect} from 'bun:test';
import {mkdtemp,mkdir,writeFile,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {PNG} from 'pngjs';
import {compareCase} from './compare-case.mjs';
async function run(unstable){
 const root=await mkdtemp(join(tmpdir(),'compare-case-'));let created=0;
 try{
  const factory=name=>async()=>{created++;return{name};};
  const result=await compareCase({browser:{},adapterFactories:{reference:factory('reference'),tau:factory('tau')},state:{},viewport:{width:2,height:2},theme:'light',outDir:root,capture:async({adapter,outDir,repeat})=>{
   await mkdir(outDir,{recursive:true});const image=new PNG({width:2,height:2});image.data.fill(255);
   if(unstable&&repeat===2)image.data[0]=254;
   await writeFile(join(outDir,'original.png'),PNG.sync.write(image));return{passed:true,name:adapter.name,assets:{app:{resolvedPath:'/fixture/app.js',sha256:'same',size:4}}};
  }});
  expect(created).toBe(4);expect(result.passed).toBe(!unstable);
  if(unstable){expect(result.comparisons.every(c=>c.exactMatch)).toBe(true);expect(result.hosts.reference.stable).toBe(false);}
  expect(JSON.parse(await readFile(join(root,'comparison.json'),'utf8')).passed).toBe(!unstable);
 }finally{await rm(root,{recursive:true,force:true});}
}
test('identical stable hosts pass with two fresh adapters each',()=>run(false));
test('matching cross-host pixels cannot hide unstable repeats',()=>run(true));
test('capture failure preserves later host attempts and complete report',async()=>{
 const root=await mkdtemp(join(tmpdir(),'compare-failures-'));const attempted=[];
 try{
  await expect(compareCase({browser:{},adapterFactories:{reference:()=>({name:'reference'}),tau:()=>({name:'tau'})},state:{},viewport:{width:2,height:2},theme:'light',outDir:root,capture:async({adapter,outDir,repeat})=>{
   attempted.push(`${adapter.name}#${repeat}`);await mkdir(outDir,{recursive:true});
   if(adapter.name==='reference'&&repeat===1)throw new Error('reference readiness failed');
   const image=new PNG({width:2,height:2});image.data.fill(255);await writeFile(join(outDir,'original.png'),PNG.sync.write(image));
   return{passed:true,assets:{app:{resolvedPath:'/fixture/app.js',sha256:'same',size:4}}};
  }})).rejects.toThrow('reference#1');
  expect(attempted).toEqual(['reference#1','reference#2','tau#1','tau#2']);
  const report=JSON.parse(await readFile(join(root,'comparison.json'),'utf8'));
  expect(report.failures).toEqual([{host:'reference',repeat:1,error:'reference readiness failed'}]);
  expect(report.hosts.tau.stable).toBe(true);
 }finally{await rm(root,{recursive:true,force:true});}
});
test('asset changes reject even pixel-identical captures',async()=>{
 const root=await mkdtemp(join(tmpdir(),'compare-assets-'));
 try{
  await expect(compareCase({browser:{},adapterFactories:{reference:()=>({name:'reference'}),tau:()=>({name:'tau'})},state:{},viewport:{width:2,height:2},theme:'light',outDir:root,capture:async({outDir,repeat})=>{
   await mkdir(outDir,{recursive:true});const image=new PNG({width:2,height:2});image.data.fill(255);
   await writeFile(join(outDir,'original.png'),PNG.sync.write(image));
   return{passed:true,assets:{app:{resolvedPath:'/fixture/app.js',sha256:String(repeat),size:4}}};
  }})).rejects.toThrow('asset identity changed');
  const report=JSON.parse(await readFile(join(root,'comparison.json'),'utf8'));
  expect(report.passed).toBe(false);expect(report.hosts.reference.captures).toHaveLength(2);
 }finally{await rm(root,{recursive:true,force:true});}
});
