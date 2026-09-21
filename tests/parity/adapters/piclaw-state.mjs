export function piclawChatId(key){
 if(key==='main')return 'web:default';
 if(key==='research')return 'web:research';
 throw new Error(`Unmapped canonical Piclaw session: ${key}`);
}
export function piclawChats(state){
 return state.sessions.map(session=>({chat_jid:piclawChatId(session.key),agent_name:session.name,
 root_chat_jid:piclawChatId(session.parentKey||session.key),
 model:`${state.model.provider}/${state.model.id}`,is_active:session.running,
 archived_at:session.archived?session.updatedAt:null,pinned:session.pinned,
 created_at:session.createdAt,updated_at:session.updatedAt,message_count:session.messageCount}));
}
export function piclawPosts(state,key=state.currentSession){
 return state.messages.filter(message=>message.sessionKey===key).map(message=>({
 id:message.id,timestamp:message.at,reply_count:0,
 data:{type:message.role==='user'?'user_message':'agent_response',content:message.text,
 ...(message.role==='assistant'?{agent_id:'default',is_bot_message:true}:{}),
 chat_jid:piclawChatId(message.sessionKey),media_ids:[]},
 })).reverse();
}
export function piclawQueue(state,key=state.currentSession){
 return state.queue.filter(item=>item.sessionKey===key).map(item=>({row_id:item.id,
 content:item.text,position:item.position,mode:item.mode,chat_jid:piclawChatId(item.sessionKey),agent_id:'default'}));
}
export function piclawMetrics(state){
 return {...structuredClone(state.metrics),process_memory:{rss_bytes:state.metrics.process_rss_bytes,vm_rss_bytes:state.metrics.process_rss_bytes}};
}
