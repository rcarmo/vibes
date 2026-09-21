import {readFile,realpath} from 'node:fs/promises';
import {createHash} from 'node:crypto';

/** Pin actual bytes and resolved release paths, not mutable symlink names alone. */
export async function snapshotAssets(files) {
  const entries=Object.entries(files);
  if(!entries.length)throw new Error('Asset manifest must not be empty');
  const result={};
  for(const [name,path] of entries){
    const resolvedPath=await realpath(path);
    const bytes=await readFile(resolvedPath);
    result[name]={path,resolvedPath,size:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
  }
  return result;
}

export async function verifyAssets(snapshot) {
  if(!Object.keys(snapshot).length)throw new Error('Asset snapshot must not be empty');
  const current=await snapshotAssets(Object.fromEntries(Object.entries(snapshot).map(([name,item])=>[name,item.path])));
  for(const [name,expected] of Object.entries(snapshot)){
    const actual=current[name];
    if(actual.sha256!==expected.sha256||actual.resolvedPath!==expected.resolvedPath)throw new Error(`Asset changed during capture: ${name}`);
  }
  return current;
}
