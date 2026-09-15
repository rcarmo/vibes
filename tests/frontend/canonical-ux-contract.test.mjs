import {test,expect} from 'bun:test';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
const feature=new URL('../ux/features/canonical-ux.feature',import.meta.url);
test('vendored canonical Piclaw UX contract is byte-identical to agreed revision',()=>{
 const bytes=readFileSync(feature);
 expect(createHash('sha256').update(bytes).digest('hex')).toBe('9219ddb5f3f403ba8c53ee11d9314ac64aaebd00f3cb08e9b3cdb0676819394c');
 const text=bytes.toString();
 for(const flow of ['workspace menu','Plan','session picker','queued item','model','active turn','attachment','read aloud','Type on the idle timeline to open Quick actions'])expect(text).toContain(flow);
 expect(text).toContain('@safety-deviation');
});
