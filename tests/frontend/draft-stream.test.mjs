import { test, expect } from 'bun:test';
import { applyDraftEvent } from '../../src/vibes/static/js/components/draft-stream.js';

test('Copilot word chunks accumulate in collapsed draft',()=>{
 let text='';
 for(const chunk of ['This ', 'is ', 'a ', 'draft.'])text=applyDraftEvent(text,'agent_draft',{text:chunk,mode:'append'},false);
 expect(text).toBe('This is a draft.');
});
test('replacement previews do not duplicate cumulative Pi text',()=>{
 let text=applyDraftEvent('','agent_draft',{text:'Hello',mode:'replace'},false);
 text=applyDraftEvent(text,'agent_draft',{text:'Hello world',mode:'replace'},false);
 expect(text).toBe('Hello world');
 expect(applyDraftEvent(text,'agent_draft',{text:'legacy snapshot'},false)).toBe('legacy snapshot');
});
test('expanded panels consume only deltas, collapsed panels only previews',()=>{
 expect(applyDraftEvent('Hello','agent_draft',{text:' world',mode:'append'},true)).toBeNull();
 expect(applyDraftEvent('Hello','agent_draft_delta',{delta:' world'},true)).toBe('Hello world');
 expect(applyDraftEvent('Hello world','agent_draft_delta',{delta:' world'},false)).toBeNull();
 expect(applyDraftEvent('old','agent_draft_delta',{delta:'fresh',reset:true},true)).toBe('fresh');
});
test('empty replacement and malformed data are bounded to text semantics',()=>{
 expect(applyDraftEvent('old','agent_draft',{text:'',mode:'replace'},false)).toBe('');
 expect(applyDraftEvent('old','agent_draft',{text:{bad:true},mode:'append'},false)).toBe('old');
});
