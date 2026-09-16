import { state, metrics } from './state.mjs';
const chat = 'web:default';
export function fixturePosts(scenario) {
  const posts = state.messages.map(m => ({ id: m.id, timestamp: m.at, reply_count: 0, chat_jid: chat,
    data: { type: m.role === 'user' ? 'user_message' : 'agent_response', content: m.text,
      agent_id: m.role === 'assistant' ? 'default' : undefined, agent_name: state.agent.name, agent_avatar: state.agent.avatar,
      user_name: state.user.name, user_avatar: state.user.avatar, session_id: 'default', media_ids: [] } }));
  if (scenario === 'attachment') posts.push({ id: 103, timestamp: state.now, chat_jid: chat, reply_count: 0,
    data: { type: 'agent_response', agent_id: 'default', content: 'Attached the layout chart.', session_id: 'default',
      media_ids: [7], content_blocks: [{ type: 'image', name: 'chart.png', media_id: 7, content_type: 'image/png' }] } });
  return posts;
}
export function apiResponse(app, path, scenario) {
  const working = scenario === 'working';
  const status = { type: 'tool_use', title: state.status, turn_id: 'fixture-turn', agent_id: 'default', session_id: 'default', chat_jid: chat };
  const modelState = { model: state.model, current: `${state.model.provider}/${state.model.id}`, thinking_level: state.thinking,
    supports_thinking: true, available: true, session_id: 'default', models: [state.model], thinking_levels: ['off', 'low', 'medium', 'high'] };
  const sessions = state.sessions.map((s,i) => ({ ...s, created_at: state.messages[0].at, updated_at: state.now, archived: false, pinned: false,
    parent_id: null, is_running: working && i === 0, message_count: 2, queued_count: working && i === 0 ? 1 : 0, last_message_at: state.messages[1].at }));
  const agents = { agents: [{ id: 'default', name: state.agent.name, avatar_url: state.agent.avatar, avatar: state.agent.avatar,
    model: modelState.current, backend: 'pi', status: working ? 'running' : 'idle', supports_thinking: true, thinking_level: state.thinking }],
    user: { name: state.user.name, avatar_url: state.user.avatar } };
  const context = { ...state.context, contextWindow: state.context.window, context_window: state.context.window,
    max_tokens: state.context.window, used_tokens: state.context.tokens, total_tokens: state.context.tokens, source: 'pi', usage: { input: 16000, output: 384, totalTokens: 16384 } };
  const queue = working ? [{ row_id: 201, id: 201, content: state.queue, text: state.queue, media_ids: [], session_id: 'default', chat_jid: chat, timestamp: state.now }] : [];
  if (path === '/timeline') return { posts: fixturePosts(scenario), has_more: false };
  if (path === '/agents' || path === '/agent/roster') return agents;
  if (path === '/agent/context') return context;
  if (path === '/system/metrics' || path === '/agent/system-metrics') return metrics();
  if (path === '/agent/models' || path.endsWith('/model-state')) return app === 'piclaw' ? { ...modelState, model: modelState.current, models: [modelState.current], model_options: [{ ...state.model, key: modelState.current, label: modelState.current, thinking_levels: ['off', 'low', 'medium', 'high'] }]} : modelState;
  if (path.endsWith('/models')) return { ...modelState, models: [state.model], providers: [] };
  if (path === '/model-preferences') return { version: 1, pins: [] };
  if (path === '/sessions') return { sessions, runtime_isolation: false };
  if (/^\/sessions\/[^/]+\/plan$/.test(path)) return { markdown: '', revision: 0, updated_at: null };
  if (path === '/agent/status') return { status: working ? status : null, active: working,
    thought: { text: working ? state.thought : '', totalLines: 2 }, draft: { text: working ? state.draft : '', totalLines: 2 }, plan: '', pending_request: null };
  if (path === '/agents/status') return { busy: working, pi_busy: working, acp_busy: false,
    active_turns: working ? [{ ...status, thread_id: 101, last_status: status }] : [], queued_followups: queue, pending_steers: [] };
  if (path === '/agent/queue') return { items: queue };
  if (path === '/agent/queue-state') return { queued_followups: queue, pending_steers: [], items: queue };
  if (path === '/agent/commands') return { commands: state.commands };
  if (path === '/agent/active-chats' || path === '/agent/branches') return { chats: state.sessions.map((s,i) => ({
    chat_jid: i ? `web:default:branch:${s.id}` : chat, agent_name: s.name, name: s.name, display_name: s.name,
    is_active: working && !i, archived_at: null, agent_id: 'default', message_count: 2, parent_chat_jid: i ? chat : null })) };
  if (path.startsWith('/agent/turn/')) return { thought: state.thought, draft: state.draft, status: 'ok' };
  if (path === '/workspace/tree') return { path: '', entries: [], tree: [], files: [], root: 'workspace', truncated: false };
  if (path === '/terminal/session') return { enabled: false };
  if (path === '/manifest.json') return { name: state.agent.name, short_name: state.agent.name, start_url: '/', display: 'standalone', icons: [] };
  if (path === '/agent/addons/web-entries') return { entries: [] };
  if (path === '/workspace/index-status') return { state: 'ready', status: 'ready', indexed_files: 0, total_files: 0, ready: true };
  if (path === '/workspace/visibility' || path === '/agent/push/presence') return { status: 'ok' };
  if (path === '/agent/settings/quick-actions' || path === '/agent/quick-actions/settings') return { settings: { workspaceCommands: ['toggle-workspace', 'open-explorer'], slashCommands: null } };
  if (path === '/agent/autoresearch/status') return { active: false };
  if (path === '/media/7/info') return { id: 7, filename: 'chart.png', content_type: 'image/png', metadata: { width: 400, height: 120, size: 1500 } };
  if (path === '/agent/model-preferences') return { version: 1, pins: [] };
  if (path === '/agent/settings-data') return { ...modelState, models: [state.model], general: {}, settings: {} };
  return undefined;
}
export function events(app, scenario) {
  const modelEvent = app === 'piclaw' ? ['model_changed', {chat_jid: chat, model: `${state.model.provider}/${state.model.id}`, current: `${state.model.provider}/${state.model.id}`, models: [`${state.model.provider}/${state.model.id}`], thinking_level: state.thinking, supports_thinking: true}] : ['session_model_changed', {session_id: 'default', model: state.model, thinking_level: state.thinking}];
  if (scenario !== 'working') return [modelEvent];
  const scope = { session_id: 'default', chat_jid: chat, turn_id: 'fixture-turn', agent_id: 'default', thread_id: 101 };
  return [ modelEvent, ['agent_status', { ...scope, type: 'thinking', title: state.status }],
    ['agent_draft', { ...scope, text: state.draft, mode: 'replace', total_lines: 2 }],
    ['agent_thought', { ...scope, text: state.thought, mode: 'replace', total_lines: 2 }],
    ['agent_status', { ...scope, type: 'tool_use', title: state.status }] ];
}
