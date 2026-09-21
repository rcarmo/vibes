import {test,expect} from 'bun:test';
import {createRequestDispatcher} from './routes.mjs';
const request=(path,method='GET')=>({url:()=>`http://fixture${path}`,method:()=>method});
test('exact routing rejects broad path lookalikes and wrong methods',async()=>{
 const router=createRequestDispatcher([{method:'GET',path:'/plan',respond:()=>({revision:1})}]);
 expect(await router.dispatch(request('/plan'))).toEqual({revision:1});
 await expect(router.dispatch(request('/plan-delete'))).rejects.toThrow('Unknown');
 await expect(router.dispatch(request('/plan','POST'))).rejects.toThrow('Unknown');
 expect(()=>router.assertRequests()).toThrow('failures');
});
test('queries require explicit validation and preserve session failures',async()=>{
 const router=createRequestDispatcher([{method:'GET',path:'/plan',validate:({url})=>{if(url.searchParams.get('chat_jid')!=='web:default'||[...url.searchParams.keys()].some(k=>k!=='chat_jid'))throw new Error('Wrong scope');},respond:()=>({})}]);
 await router.dispatch(request('/plan?chat_jid=web%3Adefault'));
 await expect(router.dispatch(request('/plan?chat_jid=other'))).rejects.toThrow('scope');
 expect(router.failures).toHaveLength(1);
 const strict=createRequestDispatcher([{method:'GET',path:'/plan',respond:()=>({})}]);
 await expect(strict.dispatch(request('/plan?ignored=true'))).rejects.toThrow('Undeclared');
});
test('duplicate routes fail before a browser is launched',()=>{
 const route={method:'GET',path:'/plan',respond:()=>({})};
 expect(()=>createRequestDispatcher([route,route])).toThrow('Duplicate');
});
