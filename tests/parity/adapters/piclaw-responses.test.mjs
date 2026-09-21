import {test,expect} from 'bun:test';
import {createCaseState} from '../canonical-state.mjs';
import {createRequestDispatcher} from '../routes.mjs';
import {piclawReadRoutes} from './piclaw-responses.mjs';
const req=path=>({url:()=>`http://fixture${path}`,method:()=> 'GET'});
test('Piclaw Plan routing rejects wrong chat and undeclared query',async()=>{
 const state=createCaseState('plan-open'),router=createRequestDispatcher(piclawReadRoutes(state));
 const path='/agent/addons/api/plan-sidebar/plan';
 expect((await router.dispatch(req(path+'?chat_jid=web%3Adefault'))).markdown).toBe(state.plan.markdown);
 await expect(router.dispatch(req(path+'?chat_jid=web%3Aresearch'))).rejects.toThrow('scope');
 await expect(router.dispatch(req(path+'?ignored=1'))).rejects.toThrow('Unexpected');
});
test('Piclaw native metrics retain canonical cache and RSS values',async()=>{
 const router=createRequestDispatcher(piclawReadRoutes(createCaseState('idle')));
 const response=await router.dispatch(req('/agent/system-metrics'));
 expect(response.buffer_cache_bytes).toBe(2147483648);expect(response.process_memory.rss_bytes).toBe(104857600);
 await expect(router.dispatch(req('/agent/system-metrics-extra'))).rejects.toThrow('Unknown');
});
test('session picker previews stay isolated to declared sessions',async()=>{
 const state=createCaseState('sessions');
 state.messages.push({id:999,sessionKey:'research',role:'user',text:'Research only',at:state.now});
 const router=createRequestDispatcher(piclawReadRoutes(state));
 const preview=await router.dispatch(req('/timeline?chat_jid=web%3Aresearch&limit=10'));
 expect(preview.posts.map(post=>post.id)).toEqual([999]);
 const main=await router.dispatch(req('/timeline?chat_jid=web%3Adefault&limit=10'));
 expect(main.posts.some(post=>post.id===999)).toBe(false);
 await expect(router.dispatch(req('/timeline?chat_jid=web%3Aunknown'))).rejects.toThrow('scope');
 await expect(router.dispatch(req('/agent/context?chat_jid=web%3Aresearch'))).rejects.toThrow('scope');
});
