import {test,expect} from 'bun:test';
import {createEventServer} from './events.mjs';
test('native stream remains open, carries explicit events, and closes cleanly',async()=>{
 const server=await createEventServer(['/api/events']);
 try{
  const response=await fetch(server.origin+'/api/events');expect(response.headers.get('content-type')).toBe('text/event-stream');
  const reader=response.body.getReader();expect(new TextDecoder().decode((await reader.read()).value)).toContain('connected');
  expect(server.clients('/api/events')).toBe(1);
  server.emit('/api/events','tau.plan.updated',{session_id:'web:default',revision:2});
  const frame=new TextDecoder().decode((await reader.read()).value);expect(frame).toContain('event: tau.plan.updated');expect(frame).toContain('"revision":2');
  server.assertRequests();await reader.cancel();
 }finally{await server.dispose();}
});
test('unknown stream requests and event injection are rejected',async()=>{
 const server=await createEventServer(['/sse/stream']);
 try{
  expect((await fetch(server.origin+'/other')).status).toBe(404);
  expect(()=>server.assertRequests()).toThrow('Unexpected');
  expect(()=>server.emit('/sse/stream','bad\nevent',{})).toThrow('Invalid');
  expect(()=>server.emit('/sse/stream','agent_status',{})).toThrow('No connected');
 }finally{await server.dispose();}
});
test('SSE query scope must be explicitly validated',async()=>{
 const strict=await createEventServer(['/api/events']);
 try{expect((await fetch(strict.origin+'/api/events?chat=other')).status).toBe(400);expect(()=>strict.assertRequests()).toThrow('query');}
 finally{await strict.dispose();}
 const scoped=await createEventServer(['/sse/stream'],{validate:({url})=>{if(url.searchParams.get('chat_jid')!=='web:default'||[...url.searchParams.keys()].some(k=>k!=='chat_jid'))throw new Error('Wrong chat scope');}});
 try{
  expect((await fetch(scoped.origin+'/sse/stream?chat_jid=other')).status).toBe(400);
  expect(()=>scoped.assertRequests()).toThrow('Wrong chat scope');
 }finally{await scoped.dispose();}
});
