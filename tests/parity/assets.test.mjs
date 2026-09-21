import {test,expect} from 'bun:test';
import {mkdtemp,writeFile,rm,symlink,unlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {snapshotAssets,verifyAssets} from './assets.mjs';
test('asset pinning rejects byte changes and release symlink changes',async()=>{
 const root=await mkdtemp(join(tmpdir(),'ui-assets-'));
 try{
  const a=join(root,'a.js'),b=join(root,'b.js'),live=join(root,'live.js');
  await writeFile(a,'same');await writeFile(b,'same');await symlink(a,live);
  const snapshot=await snapshotAssets({app:live});await verifyAssets(snapshot);
  await unlink(live);await symlink(b,live);
  await expect(verifyAssets(snapshot)).rejects.toThrow('Asset changed');
  const next=await snapshotAssets({app:live});await writeFile(b,'changed');
  await expect(verifyAssets(next)).rejects.toThrow('Asset changed');
 }finally{await rm(root,{recursive:true,force:true});}
});
test('empty asset manifests are rejected',async()=>{
 await expect(snapshotAssets({})).rejects.toThrow('empty');
});
