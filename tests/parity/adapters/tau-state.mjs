export function tauSessionId(key){
 if(key==='main')return 'web:default';
 if(key==='research')return 'web:research';
 throw new Error(`Unmapped canonical Tau session: ${key}`);
}
export function tauSession(state,session){
 return {session_id:tauSessionId(session.key),title:session.name,provider_name:state.model.provider,
 model:state.model.id,thinking_level:state.thinking,created_at:session.createdAt,updated_at:session.updatedAt,
 archived_at:session.archived?session.updatedAt:null,metadata:{}};
}
export function tauMessages(state,key){
 return state.messages.filter(message=>message.sessionKey===key).map(message=>({
 message_id:message.id,session_id:tauSessionId(message.sessionKey),role:message.role,
 created_at:message.at,content:message.text,
 }));
}
export function tauQueue(state,key){
 return state.queue.filter(item=>item.sessionKey===key).map(item=>({queue_id:String(item.id),
 session_id:tauSessionId(item.sessionKey),content:item.text,position:item.position,
 queue_kind:item.mode==='steer'?'steer':'follow_up',consumed_at:null}));
}
export function tauMetrics(state){
 const metrics=state.metrics;
 return {cpu_percent:metrics.cpu_percent,ram_percent:metrics.ram_percent,swap_percent:metrics.swap_percent,
 process_rss_bytes:metrics.process_rss_bytes,cpu_series:[...metrics.cpu_series],ram_series:[...metrics.ram_series],
 swap_series:[...metrics.swap_series],process_rss_series_bytes:[...metrics.process_rss_series_bytes],
 buffer_cache_bytes:metrics.buffer_cache_bytes,buffer_cache_series_bytes:[...metrics.buffer_cache_series_bytes],
 sample_interval_ms:metrics.sample_interval_ms,platform:metrics.platform};
}
/** These are product gaps, not exemptions or altered canonical inputs. */
export function tauStateGaps(state){
 const gaps=[];
 if(state.ui.metersEnabled&&state.metrics.buffer_cache_bytes>0)gaps.push('buffer-cache-metric');
 return gaps;
}
