import {test,expect} from 'bun:test';
import {createCaseState} from '../canonical-state.mjs';
import {tauSessionId,tauSession,tauMessages,tauQueue,tauMetrics,tauStateGaps} from './tau-state.mjs';
test('Tau mapping preserves semantic state and native session isolation',()=>{
 const state=createCaseState('queued'),before=JSON.stringify(state);
 expect(tauSessionId('main')).toBe('web:default');expect(()=>tauSessionId('unknown')).toThrow('Unmapped');
 expect(tauSession(state,state.sessions[0]).title).toBe('Fixture session');
 expect(tauMessages(state,'main')[0].content).toBe(state.messages[0].text);
 expect(tauMessages(state,'research')).toEqual([]);
 expect(tauQueue(state,'main')[0].queue_id).toBe('201');expect(tauQueue(state,'research')).toEqual([]);
 expect(tauMetrics(state).cpu_series).toEqual([10,15,25]);expect(JSON.stringify(state)).toBe(before);
});
test('canonical unsupported metrics/context stay explicit gaps',()=>{
 expect(tauStateGaps(createCaseState('idle'))).toContain('buffer-cache-metric');
 expect(tauStateGaps(createCaseState('working'))).not.toContain('token-context-usage');
 expect(tauStateGaps(createCaseState('quick-actions'))).not.toContain('quick-actions');
});
test('zero canonical token usage is still a required context capability',()=>{
 const state=createCaseState('idle');expect(state.context.tokens).toBe(0);
 expect(tauStateGaps(state)).not.toContain('token-context-usage');
});
