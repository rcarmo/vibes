import {test,expect} from 'bun:test';
import {assertMessageHoverReady} from './message-hover-ready.mjs';
test('message hover readiness targets the declared canonical post',async()=>{
 const calls=[];
 const page={locator(selector){calls.push(['locator',selector]);return{waitFor:async options=>calls.push(['waitFor',options]),hover:async()=>calls.push(['hover'])}},waitForFunction:async(fn,id)=>calls.push(['waitForFunction',id])};
 await assertMessageHoverReady(page,{ui:{hoverMessageId:102}});
 expect(calls).toEqual([['locator','#post-102'],['waitFor',{state:'visible'}],['hover'],['waitForFunction',102]]);
});
