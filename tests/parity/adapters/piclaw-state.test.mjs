import {test,expect} from 'bun:test';
import {createCaseState} from '../canonical-state.mjs';
import {piclawChatId,piclawChats,piclawPosts,piclawQueue,piclawMetrics} from './piclaw-state.mjs';
test('Piclaw maps native identity without altering canonical keys',()=>{
 const state=createCaseState('sessions'),before=JSON.stringify(state);
 const chats=piclawChats(state);expect(chats[0].chat_jid).toBe('web:default');expect(chats[1].root_chat_jid).toBe('web:default');
 expect(()=>piclawChatId('missing')).toThrow('Unmapped');expect(JSON.stringify(state)).toBe(before);
});
test('Piclaw posts preserve roles/text and explicit descending timeline order',()=>{
 const state=createCaseState('populated');const posts=piclawPosts(state);
 expect(posts.map(post=>post.id)).toEqual([102,101]);expect(posts[0].data.type).toBe('agent_response');
 expect(posts[1].data.type).toBe('user_message');expect(posts[0].data.content).toBe(state.messages[1].text);
 expect(piclawPosts(state,'research')).toEqual([]);
});
test('Piclaw metrics and queue retain canonical samples and ownership',()=>{
 const state=createCaseState('queued');const metrics=piclawMetrics(state);
 expect(metrics.process_memory.rss_bytes).toBe(104857600);expect(metrics.buffer_cache_bytes).toBe(2147483648);
 metrics.cpu_series.push(99);expect(state.metrics.cpu_series).toEqual([10,15,25]);
 expect(piclawQueue(state).map(item=>item.row_id)).toEqual([201,202]);expect(piclawQueue(state,'research')).toEqual([]);
});
