import { readFile } from 'node:fs/promises';
import { resolve, relative, extname, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { createRequestDispatcher } from '../routes.mjs';
import { fixtureAvatars } from '../canonical-state.mjs';
import { assertModelPickerReady } from './model-ready.mjs';
import { assertMessageHoverReady } from './message-hover-ready.mjs';

export const vibesCapabilities = Object.freeze({ planSidebar: true, planTool: true, speechPlayback: true, queue: true, activity: true, sessions: true, models: true, quickActions: true, workspace: true });
export const vibesSessionId = key => key === 'main' ? 'default' : key;
export function vibesResponses(state) {
  const sid = vibesSessionId(state.currentSession), active = state.activity.active;
  const scope = { session_id: sid, agent_id: 'default', turn_id: state.activity.turnKey, thread_id: 101 };
  const modelState = { model: state.model, current: `${state.model.provider}/${state.model.id}`, thinking_level: state.thinking, supports_thinking: state.model.reasoning, available: true, session_id: sid, models: [state.model], thinking_levels: state.model.thinkingLevels };
  const queue = state.queue.map(item => ({ row_id: item.id, id: item.id, content: item.text, text: item.text, session_id: vibesSessionId(item.sessionKey), media_ids: [], position: item.position }));
  return {
    '/timeline': { posts: state.messages.map(m => ({ id: m.id, timestamp: m.at, reply_count: 0, data: { type: m.role === 'user' ? 'user_message' : 'agent_response', content: m.text, agent_id: m.role === 'assistant' ? 'default' : undefined, session_id: vibesSessionId(m.sessionKey), media_ids: [] } })), has_more: false },
    [`/sessions/${sid}/plan`]: { session_id: sid, markdown: state.plan.markdown, revision: state.plan.revision, updated_at: null },
    '/agents': { agents: [{ id: 'default', name: state.agent.name, avatar_url: state.agent.avatar, backend: 'pi', model: modelState.current, status: active ? 'running' : 'idle' }], user: { name: state.user.name, avatar_url: state.user.avatar } },
    '/sessions': { sessions: state.sessions.map(s => ({ id: vibesSessionId(s.key), name: s.name, parent_id: s.parentKey ? vibesSessionId(s.parentKey) : null, created_at: s.createdAt, updated_at: s.updatedAt, archived: s.archived, pinned: s.pinned, is_running: s.running, message_count: s.messageCount, queued_count: s.key === state.currentSession ? queue.length : 0, model: `${state.model.provider}/${state.model.id}` })), runtime_isolation: false },
    [`/sessions/${sid}/model-state`]: modelState,
    [`/sessions/${sid}/models`]: { available: true, models: [state.model], thinking_levels: state.model.thinkingLevels },
    '/agent/models': modelState,
    '/agent/commands': { commands: state.commands },
    '/agent/context': { ...state.context, context_window: state.context.window, used_tokens: state.context.tokens, compact_command: state.context.compactCommand, source: 'pi' },
    '/agent/queue': { items: queue },
    '/agents/status': { busy: active, pi_busy: active, acp_busy: false, active_turns: active ? [{ ...scope, last_status: { ...scope, type: state.activity.type, title: state.activity.title } }] : [], queued_followups: queue, pending_steers: [] },
    '/system/metrics': { ...state.metrics, process_memory: { rss_bytes: state.metrics.process_rss_bytes, vm_rss_bytes: state.metrics.process_rss_bytes } },
    '/workspace/tree': { path: '', root: { name: 'workspace', path: '.', type: 'dir', size: null, mtime: null, children: state.workspace.entries.map(e => ({ ...e, type: e.kind })) }, truncated: false },
    '/terminal/session': { enabled: false },
    '/model-preferences': { version: 1, pins: [] },
    '/manifest.json': { name: state.agent.name, short_name: state.agent.name, icons: [], start_url: '/', display: 'standalone' },
  };
}
const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
export function createVibesAdapter({ staticRoot = resolve(repositoryRoot, 'src/vibes/static') } = {}) {
  const root = resolve(staticRoot), streams = new Set();
  let dispatcher, server;
  const failures = [];
  const mime = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
  return {
    name: 'vibes', capabilities: vibesCapabilities,
    assets: { html: resolve(root, 'index.html'), app: resolve(root, 'dist/app.js'), css: resolve(root, 'dist/app.css'), editor: resolve(root, 'js/vendor/codemirror.js') },
    async install({ page, context, state, theme }) {
      const sid = vibesSessionId(state.currentSession), responses = vibesResponses(state);
      const scoped = new Set(['/timeline', '/agent/commands', '/agent/context', '/agent/queue', '/agents/status']);
      const definitions = Object.entries(responses).map(([path, json]) => ({ method: 'GET', path, respond: () => ({ json }), validate: ({ url }) => {
        const allowed = path === '/timeline' ? ['session_id', 'limit', 'before'] : scoped.has(path) ? ['session_id'] : path === '/sessions' ? ['include_archived'] : path === '/workspace/tree' ? ['path', 'depth', 'include_hidden', 'show_hidden', 'limit'] : [];
        for (const key of url.searchParams.keys()) if (!allowed.includes(key)) throw new Error(`Undeclared query ${path}:${key}`);
        if (path === '/sessions' && !['true', 'false'].includes(url.searchParams.get('include_archived') || 'false')) throw new Error('Invalid archive query');
        if (scoped.has(path) && url.searchParams.get('session_id') !== sid) throw new Error(`Wrong session ${url}`);
      } }));
      definitions.push({ method: 'POST', path: '/workspace/visibility', respond: () => ({ json: { status: 'ok' } }) });
      if (state.activity.active) definitions.push({ method: 'POST', path: `/agent/turn/${state.activity.turnKey}/panel`, validate: ({ request }) => {
        const body=request.postDataJSON();if(!body||!['thought','draft'].includes(body.panel)||typeof body.expanded!=='boolean')throw new Error('Invalid panel state');
      }, respond: () => ({ json: { status: 'ok' } }) });
      dispatcher = createRequestDispatcher(definitions);
      server = createServer((request, response) => {
        const path = new URL(request.url, 'http://localhost').pathname;
        if (path !== '/sse/stream' || request.method !== 'GET') { failures.push(`Unexpected server request ${request.method} ${request.url}`); response.writeHead(404).end(); return; }
        response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' });
        response.write('event: connected\ndata: {}\n\n'); streams.add(response);
        response.on('close', () => streams.delete(response));
      });
      await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
      const origin = `http://127.0.0.1:${server.address().port}`;
      await context.addInitScript(({ state, theme }) => {
        localStorage.clear(); sessionStorage.clear();
        localStorage.setItem('vibes-theme', theme);
        localStorage.setItem('piclaw:plan-sidebar:open', String(state.ui.planOpen));
        localStorage.setItem('workspaceOpen', String(state.ui.workspaceOpen));
        localStorage.setItem('piclaw_compose_height', String(state.ui.composeHeight));
        localStorage.setItem('vibes_system_meters_collapsed', String(state.ui.metersCollapsed));
      }, { state, theme });
      await context.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url()), path = url.pathname;
        try {
          if (url.origin !== origin) throw new Error('External request: ' + url);
          if (path === '/sse/stream' && request.method() === 'GET' && !url.search) return route.continue();
          if ((path === '/' || path.startsWith('/static/')) && request.method() === 'GET') {
            if ([...url.searchParams.keys()].some(k => k !== 'v')) throw new Error('Unexpected asset query');
            const file = path === '/' ? resolve(root, 'index.html') : resolve(root, path.slice(8));
            if (relative(root, file).startsWith('..')) throw new Error('Asset traversal');
            return route.fulfill({ body: await readFile(file), contentType: mime[extname(file)] || 'application/octet-stream' });
          }
          if ([state.agent.avatar, state.user.avatar].includes(path) && request.method() === 'GET') {
            if ([...url.searchParams.keys()].some(k => k !== 'v') || (url.searchParams.has('v') && url.searchParams.get('v') !== String(Date.parse(state.now)))) throw new Error('Invalid avatar version');
            return route.fulfill({ contentType: 'image/svg+xml', body: fixtureAvatars[path] });
          }
          if (path === '/favicon.ico' && request.method() === 'GET' && !url.search) return route.fulfill({ status: 204, body: '' });
          return route.fulfill(await dispatcher.dispatch(request));
        } catch (error) { failures.push(error.message); await route.fulfill({ status: 500, json: { error: error.message } }); }
      });
      return { url: origin + '/' };
    },
    async ready({ page, state }) {
      if (!vibesCapabilities.planSidebar) throw new Error('Vibes capability gap: persistent Plan sidebar is not implemented');
      await page.locator('.compose-box textarea').waitFor();
      await page.locator('.plan-sidebar-toggle').waitFor();
      await page.locator('.compose-box textarea').fill(state.compose);
      const composeBox = await page.locator('.compose-box textarea').boundingBox();
      if (Math.abs(composeBox.height - state.ui.composeHeight) > 1) throw new Error('Vibes canonical compose height mismatch');
      // Registry is lazy in Vibes. Use the actual picker, then restore requested UI.
      // Opening Plan schedules editor autofocus: settle that focus before switching.
      if (state.ui.planOpen) { await page.locator('.plan-sidebar-editor .cm-content').waitFor(); await page.waitForTimeout(100); }
      await page.getByTestId('session-switcher').focus(); await page.keyboard.press('Enter');
      await page.locator('#compose-session-search').waitFor();
      await page.locator('.compose-session-popup-close').evaluate(button => button.click());
      await page.waitForFunction(name => document.querySelector('[data-testid="session-switcher"]')?.textContent.includes(name), state.sessions.find(s => s.key === state.currentSession).name);
      if (state.ui.planOpen) await page.waitForFunction(markdown => [...document.querySelectorAll('.plan-sidebar-editor .cm-line')].map(line => line.textContent).join('\n') === markdown, state.plan.markdown);
      const expected = state.messages.filter(m => m.sessionKey === state.currentSession).map(m => m.id);
      for (const id of expected) await page.locator(`#post-${id}`).waitFor();
      const actual = await page.locator('.timeline .post').evaluateAll(posts => posts.map(post => Number(post.id.replace('post-', ''))));
      if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error('Vibes message order mismatch');
      if (state.ui.popup === 'sessions') { await page.getByTestId('session-switcher').click(); await page.locator('#compose-session-search').waitFor(); }
      await assertModelPickerReady(page, state);
      if (state.ui.popup === 'quick-actions') {
        await page.locator('.timeline').click(); await page.keyboard.type('m');
        await page.locator('.timeline-quick-actions-input').fill('');
      }
      await assertMessageHoverReady(page, state);
      if (state.activity.active) {
        const scope = { session_id: vibesSessionId(state.currentSession), agent_id: 'default', turn_id: state.activity.turnKey, thread_id: 101 };
        const body = { ...scope, type: state.activity.type === 'tool_use' ? 'tool_call' : state.activity.type, title: state.activity.title, tool_name: state.activity.type === 'tool_use' ? 'fixture' : undefined };
        for (const stream of streams) stream.write(`event: agent_status\ndata: ${JSON.stringify(body)}\n\n`);
        await page.getByText(state.activity.title, { exact: false }).waitFor({ state: 'visible' });
      }
    },
    assertRequests() { dispatcher?.assertRequests(); if (failures.length) throw new Error(failures.join('; ')); },
    async dispose() { for (const stream of streams) stream.end(); if (server) await new Promise(resolve => server.close(resolve)); },
  };
}
