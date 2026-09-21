import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {PNG} from 'pngjs';
import {captureCase} from './capture.mjs';
import {compareImages,overlayImages,assessRepeats} from './images.mjs';

/** Each adapter factory must return fresh request/state tracking per capture. */
export async function compareCase({browser,adapterFactories,state,viewport,theme,outDir,repeats=2,capture=captureCase}) {
  if(!Number.isInteger(repeats)||repeats<2)throw new Error('At least two repeats are required');
  const names=Object.keys(adapterFactories);
  if(names.length<2)throw new Error('At least two hosts are required');
  await mkdir(outDir,{recursive:true});
  const report={viewport,theme,repeats,hosts:{},comparisons:[],failures:[],passed:false};
  const images={};
  try{
    for(const name of names){
      images[name]=[];
      const captures=[];report.hosts[name]={captures,stable:false};
      for(let repeat=1;repeat<=repeats;repeat++){
        const directory=join(outDir,name,`repeat-${repeat}`);
        try {
          const adapter=await adapterFactories[name]();
          const result=await capture({browser,adapter,state:structuredClone(state),viewport,theme,outDir:directory,repeat});
          if(!result.passed)throw new Error(`${name} repeat ${repeat} did not pass capture checks`);
          if(!result.assets||Object.keys(result.assets).length===0)throw new Error(`${name}: missing pinned assets`);
          const identity=assets=>JSON.stringify(Object.entries(assets).sort(([a],[b])=>a.localeCompare(b)).map(([key,item])=>[key,item.resolvedPath,item.sha256,item.size]));
          if(repeat>1&&captures[0]?.assets&&identity(result.assets)!==identity(captures[0].assets))throw new Error(`${name}: asset identity changed between repeats`);
          captures.push(result);
          images[name][repeat-1]=PNG.sync.read(await readFile(join(directory,'original.png')));
        } catch(error) {
          const failure={host:name,repeat,error:error.message};
          report.failures.push(failure);captures.push({passed:false,...failure});
          try { images[name][repeat-1]=PNG.sync.read(await readFile(join(directory,'original.png'))); } catch {}
        }
      }
      const complete=images[name].filter(Boolean);
      if(complete.length===repeats){
        const stability=assessRepeats(complete);Object.assign(report.hosts[name],stability);
        for(let i=1;i<repeats;i++){
          const result=compareImages(images[name][0],images[name][i]);
          await writeFile(join(outDir,name,`repeat-diff-${i+1}.png`),PNG.sync.write(result.diff));
        }
      }
    }
    const reference=names[0];
    for(const name of names.slice(1))for(let i=0;i<repeats;i++){
      const left=images[reference][i],right=images[name][i];if(!left||!right)continue;
      const {diff,...metrics}=compareImages(left,right),prefix=`${reference}-vs-${name}-repeat-${i+1}`;
      await writeFile(join(outDir,`${prefix}-diff.png`),PNG.sync.write(diff));
      await writeFile(join(outDir,`${prefix}-overlay.png`),PNG.sync.write(overlayImages(left,right)));
      report.comparisons.push({reference,host:name,repeat:i+1,...metrics});
    }
    report.passed=!report.failures.length&&Object.values(report.hosts).every(host=>host.stable)&&report.comparisons.length===(names.length-1)*repeats&&report.comparisons.every(item=>item.exactMatch);
    if(report.failures.length)throw new Error(`Capture failures: ${report.failures.map(item=>`${item.host}#${item.repeat}: ${item.error}`).join('; ')}`);
    return report;
  }catch(error){report.failure=error.message;throw error;}
  finally{await writeFile(join(outDir,'comparison.json'),JSON.stringify(report,null,2));}
}
