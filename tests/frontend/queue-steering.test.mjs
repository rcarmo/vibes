import {test,expect} from 'bun:test';
import {createQueueSteeringGuard} from '../../src/vibes/static/js/components/queue-steering.js';

test('steering deduplicates both in-flight and acknowledged requests',async()=>{
 const guard=createQueueSteeringGuard();let release,calls=0;
 const submit=()=>{calls++;return new Promise(resolve=>{release=resolve;});};
 const first=guard.run('chat','turn',-7,submit);
 expect(await guard.run('chat','turn',-7,submit)).toBe(false);
 release();expect(await first).toBe(true);
 expect(await guard.run('chat','turn',-7,submit)).toBe(false);
 expect(calls).toBe(1);
});
test('failure can retry and another chat/turn remains independent',async()=>{
 const guard=createQueueSteeringGuard();let calls=0;
 await expect(guard.run('chat','turn',-7,async()=>{throw Error('unavailable');})).rejects.toThrow('unavailable');
 expect(await guard.run('chat','turn',-7,async()=>{calls++;})).toBe(true);
 expect(await guard.run('other','turn',-7,async()=>{calls++;})).toBe(true);
 expect(await guard.run('chat','next',-7,async()=>{calls++;})).toBe(true);
 expect(calls).toBe(3);
});
test('late failure cannot release a newer turn claim',async()=>{
 const guard=createQueueSteeringGuard();let reject;
 const old=guard.run('chat','old',-7,()=>new Promise((_,fail)=>{reject=fail;}));
 expect(await guard.run('chat','new',-7,async()=>{})).toBe(true);
 reject(Error('old failed'));await expect(old).rejects.toThrow('old failed');
 expect(await guard.run('chat','new',-7,async()=>{throw Error('must not submit');})).toBe(false);
});
