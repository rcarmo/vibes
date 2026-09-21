import {tauSessionId,tauSession,tauMessages,tauQueue,tauMetrics} from './tau-state.mjs';

/** Native read-only response table. Mutating workflow fixtures remain separate. */
export function tauResponses(state){
 const responses={
  '/api/settings':{agent_name:state.agent.name,agent_avatar:state.agent.avatar,user_name:state.user.name,user_avatar:state.user.avatar},
  '/api/models':{source:'fixture',models:[{provider_name:state.model.provider,model:state.model.id,context_window:state.model.contextWindow,supports_thinking:state.model.reasoning,thinking_levels:[...state.model.thinkingLevels]}]},
  '/api/commands':{source:'fixture',commands:state.commands},
  '/api/extensions/frontend-modules':{modules:[]},
  '/api/sessions':{sessions:state.sessions.map(session=>tauSession(state,session))},
  '/api/files':{kind:'directory',path:'',entries:state.workspace.entries.map(entry=>({...entry}))},
  '/meters':tauMetrics(state),
 };
 for(const session of state.sessions){
  const id=tauSessionId(session.key),root=`/api/sessions/${encodeURIComponent(id)}`;
  responses[root]=tauSession(state,session);
  responses[`${root}/timeline`]={timeline:tauMessages(state,session.key)};
  responses[`${root}/queue`]={queue:tauQueue(state,session.key)};
  responses[`${root}/approvals`]={approvals:[]};
  responses[`${root}/context`]={entry_count:session.messageCount,message_count:session.messageCount,compaction_count:0,active_leaf_entry_id:null,estimated_tokens:session.key===state.currentSession?state.context.tokens:null,context_window:session.key===state.currentSession?state.context.window:null,token_usage_source:session.key===state.currentSession?'local_estimate':null,compact_command:session.key===state.currentSession?state.context.compactCommand:null};
  responses[`${root}/runs`]={runs:session.running?[{run_id:state.activity.turnKey,session_id:id,status:'running',last_status:{phase:'running',type:state.activity.type,title:state.activity.title}}]:[]};
  responses[`${root}/plan`]={markdown:state.plan.sessionKey===session.key?state.plan.markdown:'',revision:state.plan.sessionKey===session.key?state.plan.revision:0};
 }
 return responses;
}

export function tauReadRoutes(state){
 return Object.entries(tauResponses(state)).map(([path,response])=>({
  method:'GET',path,
  validate:({url})=>{
   const allowed=path==='/api/sessions'?['include_archived']:path==='/api/files'?['path']:path.endsWith('/timeline')?['limit','after']:[];
   for(const key of url.searchParams.keys())if(!allowed.includes(key))throw new Error(`Unexpected Tau query: ${path} ${key}`);
   if(path.endsWith('/timeline')){
    const after=url.searchParams.get('after')??'0',limit=url.searchParams.get('limit')??'200';
    if(!/^\d+$/.test(after)||!/^\d+$/.test(limit)||Number(limit)<1||Number(limit)>200)throw new Error('Invalid Tau timeline pagination');
   }
   if(path==='/api/files'&&url.searchParams.get('path'))throw new Error('Only canonical workspace root is declared');
   if(path==='/api/sessions'&&url.searchParams.has('include_archived')&&!['true','false'].includes(url.searchParams.get('include_archived')))throw new Error('Invalid archive scope');
  },
  respond:({url})=>{
   const value=structuredClone(response);
   if(path.endsWith('/timeline'))value.timeline=value.timeline.filter(message=>message.message_id>Number(url.searchParams.get('after')||0)).slice(0,Number(url.searchParams.get('limit')||200));
   return value;
  },
 }));
}
