import {test,expect} from 'bun:test';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
const feature=new URL('../ux/features/canonical-ux.feature',import.meta.url);
test('vendored canonical Piclaw UX contract is byte-identical to agreed revision',()=>{
 const bytes=readFileSync(feature);
 expect(createHash('sha256').update(bytes).digest('hex')).toBe('a08a623880c6f327bc051edc51bb2bbff2959aed86421b5227e61d5a92fc2441');
 const text=bytes.toString();
 for(const flow of ['workspace menu','Plan','session picker','queued item','model','active turn','attachment','read aloud','Type on the idle timeline to open Quick actions'])expect(text).toContain(flow);
 expect(text).toContain('@safety-deviation');
});
