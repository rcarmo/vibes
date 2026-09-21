import {test,expect} from 'bun:test';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const digest=value=>createHash('sha256').update(value).digest('hex');
const agreedDigest='a08a623880c6f327bc051edc51bb2bbff2959aed86421b5227e61d5a92fc2441';

test('Vibes-owned canonical copies are byte-identical to the agreed revision',async()=>{
 const canonical=await readFile(new URL('./canonical-ux.feature',import.meta.url));
 const productCopy=await readFile(resolve(import.meta.dir,'../../ux/features/canonical-ux.feature'));
 expect(productCopy.equals(canonical)).toBe(true);
 expect(digest(canonical)).toBe(agreedDigest);
});

test('canonical Gherkin declares interaction and safety gates',async()=>{
 const text=await readFile(new URL('./canonical-ux.feature',import.meta.url),'utf8');
 for(const tag of ['@shell','@workspace','@quick-actions','@skills','@plan','@session-picker','@queue','@model-picker','@turn','@timeline','@messages','@tools','@pane','@glyph','@timer','@attachments','@copy','@speech','@safety-deviation'])expect(text).toContain(tag);
 for(const phrase of ['/skill:<name>','one session-scoped "plan" tool','multiple explicit message IDs','elapsed timer','terminal glyph','Render model-generated SVG inline','unsafe elements and attributes are removed'])expect(text).toContain(phrase);
 expect(text).toContain('Piclaw currently enables idle Steer');
 expect(text).toContain('visual equality must not be achieved by enabling an unsafe action');
});
