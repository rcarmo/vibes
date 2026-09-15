import {test,expect} from 'bun:test';
import {preserveQueuedRecovery,recoverQueuedDraft,returnQueuedText} from '../../src/vibes/static/js/components/queue-return.js';
class Storage { constructor(){this.values=new Map()} getItem(k){return this.values.get(k)??null} setItem(k,v){this.values.set(k,String(v))} removeItem(k){this.values.delete(k)} }
test('queue recovery merges with latest draft once and keeps metadata',async()=>{
 const storage=new Storage(),sessionId='main';
 storage.setItem('vibes_compose_draft:main',JSON.stringify({text:'newer edit',fileRefs:['a'],messageRefs:['1']}));
 const key=preserveQueuedRecovery(storage,{sessionId,queueId:7,text:'queued text'});
 let removed=0;const result=await returnQueuedText({text:'queued text',preserve:async()=>{},remove:async()=>{removed++;return true;}});
 expect(result.removed).toBe(true);expect(removed).toBe(1);
 expect(recoverQueuedDraft(storage,key,sessionId)).toBe('newer edit\n\nqueued text');
 const draft=JSON.parse(storage.getItem('vibes_compose_draft:main'));expect(draft.fileRefs).toEqual(['a']);expect(draft.messageRefs).toEqual(['1']);
 // Replaying a retained recovery marker cannot duplicate the content.
 storage.setItem(key,JSON.stringify({sessionId,queueId:7,text:'queued text'}));
 expect(recoverQueuedDraft(storage,key,sessionId)).toBe(draft.text);
});
test('storage and removal failure retain recoverable queued text',async()=>{
 const broken={setItem(){throw new Error('quota')},getItem(){return null}};let removed=0;
 await expect(returnQueuedText({text:'queued',preserve:()=>preserveQueuedRecovery(broken,{sessionId:'main',queueId:1,text:'queued'}),remove:async()=>{removed++;return true;}})).rejects.toThrow('quota');
 expect(removed).toBe(0);
 const storage=new Storage(),key=preserveQueuedRecovery(storage,{sessionId:'main',queueId:2,text:'queued'});
 expect((await returnQueuedText({text:'queued',preserve:async()=>{},remove:async()=>false})).removed).toBe(false);
 expect(storage.getItem(key)).not.toBeNull();
 expect(()=>recoverQueuedDraft(storage,key,'other')).toThrow('Invalid queue recovery');
});
