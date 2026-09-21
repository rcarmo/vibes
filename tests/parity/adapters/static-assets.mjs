import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {snapshotAssets,verifyAssets} from '../assets.mjs';

/** Explicit URL-to-file map, including query version validation where supplied. */
export async function createStaticAssets(definitions) {
  const urls=new Map();
  for(const definition of definitions){
    if(!definition.url.startsWith('/')||urls.has(definition.url))throw new Error(`Invalid or duplicate asset URL: ${definition.url}`);
    urls.set(definition.url,definition);
  }
  const snapshot=await snapshotAssets(Object.fromEntries(definitions.map(item=>[item.url,item.path])));
  return {
    snapshot,
    async respond({request,url}){
      const definition=urls.get(url.pathname);
      if(!definition)return null;
      if(!['GET','HEAD'].includes(request.method()))throw new Error(`Invalid asset method: ${request.method()} ${url.pathname}`);
      const expected=definition.query||'';
      if(url.search!==expected)throw new Error(`Unexpected asset version: ${url.pathname}${url.search}`);
      const pinned=snapshot[url.pathname];
      const body=await readFile(pinned.resolvedPath);
      if(createHash('sha256').update(body).digest('hex')!==pinned.sha256)throw new Error(`Asset changed before serving: ${url.pathname}`);
      return {status:200,contentType:definition.contentType,headers:{'Cache-Control':'no-store'},body:request.method()==='HEAD'?Buffer.alloc(0):body};
    },
    verify:()=>verifyAssets(snapshot),
  };
}
