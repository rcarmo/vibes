import {test,expect} from 'bun:test';
import {PNG} from 'pngjs';
import {compareImages,assessRepeats} from './images.mjs';
const image=()=>{const png=new PNG({width:2,height:2});png.data.fill(255);return png;};
test('exact channel changes remain failures even below perceptual threshold',()=>{
 const a=image(),b=image();b.data[0]=254;
 const result=compareImages(a,b);expect(result.exactPixels).toBe(1);expect(result.exactMatch).toBe(false);
 expect(assessRepeats([a,b]).stable).toBe(false);
});
test('identical captures pass and mismatched dimensions are rejected',()=>{
 expect(assessRepeats([image(),image()]).stable).toBe(true);
 expect(()=>compareImages(image(),new PNG({width:3,height:2}))).toThrow('dimensions');
 expect(()=>assessRepeats([image()])).toThrow('two');
});
