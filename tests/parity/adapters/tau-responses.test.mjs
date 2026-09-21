import {test,expect} from 'bun:test';
import {createCaseState} from '../canonical-state.mjs';
import {createRequestDispatcher} from '../routes.mjs';
import {tauResponses,tauReadRoutes} from './tau-responses.mjs';
const req=path=>({url:()=>`http://fixture${path}`,method:()=> 'GET'});
test('session responses preserve native escaped paths and isolate Plan/messages',()=>{
 const state=createCaseState('sessions'),responses=tauResponses(state);
 expect(responses['/api/sessions/web%3Adefault/plan'].markdown).toBe(state.plan.markdown);
 expect(responses['/api/sessions/web%3Aresearch/plan'].markdown).toBe('');
 expect(responses['/api/sessions/web%3Aresearch/timeline'].timeline).toEqual([]);
});
test('Tau route table rejects undeclared scopes and returns independent values',async()=>{
 const router=createRequestDispatcher(tauReadRoutes(createCaseState('populated')));
 const path='/api/sessions/web%3Adefault/timeline?limit=10';
 const first=await router.dispatch(req(path));first.timeline[0].content='mutated';
 expect((await router.dispatch(req(path))).timeline[0].content).toBe('Compare the two interfaces.');
 await expect(router.dispatch(req('/api/files?path=private'))).rejects.toThrow('root');
 await expect(router.dispatch(req('/api/sessions?unknown=true'))).rejects.toThrow('Unexpected');
});
test('native ascending timeline pagination never repeats prior messages',async()=>{
 const router=createRequestDispatcher(tauReadRoutes(createCaseState('populated')));
 const root='/api/sessions/web%3Adefault/timeline';
 const first=await router.dispatch(req(root+'?after=0&limit=1'));
 expect(first.timeline.map(message=>message.message_id)).toEqual([101]);
 expect((await router.dispatch(req(root+'?after=101&limit=200'))).timeline.map(message=>message.message_id)).toEqual([102]);
 expect((await router.dispatch(req(root+'?after=102&limit=200'))).timeline).toEqual([]);
 await expect(router.dispatch(req(root+'?after=-1'))).rejects.toThrow('pagination');
 await expect(router.dispatch(req(root+'?before=102'))).rejects.toThrow('Unexpected');
});
