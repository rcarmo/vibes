import {test,expect} from 'bun:test';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createStaticAssets} from './static-assets.mjs';
const request=(path,method='GET')=>({request:{method:()=>method},url:new URL(path,'http://fixture')});
test('static responder pins bytes and rejects wrong versions/methods',async()=>{
 const root=await mkdtemp(join(tmpdir(),'static-pin-'));
 try{
  const path=join(root,'app.js');await writeFile(path,'original');
  const assets=await createStaticAssets([{url:'/app.js',query:'?v=one',path,contentType:'text/javascript'}]);
  expect((await assets.respond(request('/app.js?v=one'))).body.toString()).toBe('original');
  expect(await assets.respond(request('/unknown.js'))).toBe(null);
  await expect(assets.respond(request('/app.js?v=two'))).rejects.toThrow('version');
  await expect(assets.respond(request('/app.js?v=one','POST'))).rejects.toThrow('method');
  await writeFile(path,'changed');
  await expect(assets.respond(request('/app.js?v=one'))).rejects.toThrow('changed');
 }finally{await rm(root,{recursive:true,force:true});}
});
