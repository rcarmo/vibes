import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';
export const diffOptions = { threshold: 0.1, includeAA: false };
export function compare(a,b) {
  if(a.width!==b.width||a.height!==b.height)throw Error('Screenshots must have matching pixel dimensions');
  const diff=new PNG({width:a.width,height:a.height});
  const count=pixelmatch(a.data,b.data,diff.data,a.width,a.height,diffOptions);
  return {diff,count,ratio:count/(a.width*a.height)};
}
export function sideBySide(a,b) {
  const out=new PNG({width:a.width+b.width,height:Math.max(a.height,b.height)});
  PNG.bitblt(a,out,0,0,a.width,a.height,0,0);PNG.bitblt(b,out,0,0,b.width,b.height,a.width,0);return out;
}
export function overlay(a,b) {
  if(a.width!==b.width||a.height!==b.height)throw Error('Screenshots must match');
  const out=new PNG({width:a.width,height:a.height});
  for(let i=0;i<a.data.length;i++)out.data[i]=Math.round((a.data[i]+b.data[i])/2);
  return out;
}
export function unionRegion(a,b,selector,geometries) {
  const boxes=geometries.flatMap(g=>g[selector]||[]).filter(r=>r.width>0&&r.height>0);
  if(!boxes.length)return null;
  const x=Math.max(0,Math.floor(Math.min(...boxes.map(r=>r.x))));
  const y=Math.max(0,Math.floor(Math.min(...boxes.map(r=>r.y))));
  const right=Math.min(a.width,Math.ceil(Math.max(...boxes.map(r=>r.x+r.width))));
  const bottom=Math.min(a.height,Math.ceil(Math.max(...boxes.map(r=>r.y+r.height))));
  const width=right-x,height=bottom-y;if(width<=0||height<=0)return null;
  const crop=image=>{const out=new PNG({width,height});PNG.bitblt(image,out,x,y,width,height,0,0);return out;};
  const left=crop(a),rightImage=crop(b),result=compare(left,rightImage);
  return {...result,rect:{x,y,width,height},left,right:rightImage};
}
