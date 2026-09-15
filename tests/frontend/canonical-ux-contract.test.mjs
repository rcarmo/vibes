import {test,expect} from 'bun:test';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
const feature=new URL('../ux/features/canonical-ux.feature',import.meta.url);
test('vendored canonical Piclaw UX contract is byte-identical to agreed revision',()=>{
 const bytes=readFileSync(feature);
 expect(createHash('sha256').update(bytes).digest('hex')).toBe('ff7ead37487e42319651faa35f01a1929c1b221199b1f21f856b531b3ef31213');
 const text=bytes.toString();
 for(const flow of ['workspace menu','Plan','session picker','queued item','model','active turn','attachment','read aloud'])expect(text).toContain(flow);
 expect(text).toContain('@safety-deviation');
});
