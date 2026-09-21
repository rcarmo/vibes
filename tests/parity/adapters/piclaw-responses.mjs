import {piclawChatId,piclawChats,piclawPosts,piclawQueue,piclawMetrics} from './piclaw-state.mjs';

export function piclawReadRoutes(state){
 const current=piclawChatId(state.currentSession);
 const model={...state.model,context_window:state.model.contextWindow,thinking_levels:[...state.model.thinkingLevels]};
 const table={
  '/agent/active-chats':{chats:piclawChats(state)},
  '/agent/branches':{chats:piclawChats(state)},
  '/agent/roster':{agents:[{id:'default',name:state.agent.name,avatar_url:state.agent.avatar}],user:{name:state.user.name,avatar_url:state.user.avatar}},
  '/agent/models':{models:[model],model_options:[{label:`${state.model.provider}/${state.model.id}`,provider:state.model.provider,id:state.model.id,name:state.model.name,context_window:state.model.contextWindow,reasoning:state.model.reasoning,thinking_levels:[...state.model.thinkingLevels]}],model:`${state.model.provider}/${state.model.id}`,current:`${state.model.provider}/${state.model.id}`,thinking_level:state.thinking,thinking_levels:[...state.model.thinkingLevels],supports_thinking:state.model.reasoning},
  '/agent/context':{tokens:state.context.tokens,contextWindow:state.context.window,percent:state.context.percent,compact_command:state.context.compactCommand},
  '/agent/queue-state':{items:piclawQueue(state),count:piclawQueue(state).length},
  '/agent/status':{status:state.activity.active?'running':'idle',active_turns:[]},
  '/agent/autoresearch/status':{enabled:false},
  '/agent/commands':{commands:state.commands},
  '/agent/settings/quick-actions':{ok:true,settings:{workspaceCommands:['toggle-workspace'],slashCommands:state.commands.map(command=>command.name)}},
  '/agent/addons/web-entries':{entries:[]},
  '/agent/system-metrics':piclawMetrics(state),
  '/agent/addons/api/plan-sidebar/plan':{markdown:state.plan.markdown,revision:state.plan.revision,updated_at:null},
  '/timeline':{posts:piclawPosts(state),has_more:false},
  '/workspace/tree':{root:{name:'workspace',path:'.',type:'dir',size:null,mtime:null,child_count:state.workspace.entries.length,children:state.workspace.entries.map(entry=>({name:entry.name,path:entry.path,type:entry.kind==='directory'?'dir':'file',size:entry.kind==='directory'?null:0,mtime:state.now,child_count:entry.kind==='directory'?0:undefined,children:entry.kind==='directory'?[]:undefined}))},truncated:false},
  '/workspace/index-status':{state:'ready',indexed_file_count:state.workspace.entries.length,roots:['.']},
 };
 const queries={
  '/agent/branches':['root_chat_jid','include_archived'],
  '/agent/commands':['chat_jid'], '/agent/autoresearch/status':['chat_jid'],
  '/agent/models':['chat_jid'], '/agent/context':['chat_jid'],
  '/agent/queue-state':['chat_jid'], '/agent/status':['chat_jid'],
  '/agent/addons/api/plan-sidebar/plan':['chat_jid'],
  '/timeline':['chat_jid','limit','before'],
  '/workspace/tree':['path','depth','show_hidden'], '/workspace/index-status':['scope'],
 };
 return Object.entries(table).map(([path,response])=>({method:'GET',path,
  validate:({url})=>{
   for(const key of url.searchParams.keys())if(!(queries[path]||[]).includes(key))throw new Error(`Unexpected Piclaw query: ${path} ${key}`);
   for(const key of ['chat_jid','root_chat_jid'])if(url.searchParams.has(key)&&url.searchParams.get(key)!==current){
    const declaredPreview=path==='/timeline'&&key==='chat_jid'&&state.sessions.some(session=>piclawChatId(session.key)===url.searchParams.get(key));
    if(!declaredPreview)throw new Error(`Wrong Piclaw session scope: ${key}`);
   }
   if(path==='/agent/addons/api/plan-sidebar/plan'&&state.plan.sessionKey!==state.currentSession)throw new Error('Plan scope is not current session');
   if(path==='/workspace/tree'&&url.searchParams.get('path'))throw new Error('Only canonical workspace root declared');
  },respond:({url})=>{
   if(path==='/timeline'){
    const session=state.sessions.find(session=>piclawChatId(session.key)===(url.searchParams.get('chat_jid')||current));
    return {posts:piclawPosts(state,session.key),has_more:false};
   }
   return structuredClone(response);
  }}));
}
