// Semantic fixture contract v1. Owned by @vibes; host wire formats belong in adapters.
// Synthetic identities and content are data, never replacement product chrome.
export const canonicalState = deepFreeze({
  schemaVersion: 1,
  now: '2026-01-01T12:00:00.000Z',
  locale: 'en-US', timezone: 'UTC', deviceScaleFactor: 1,
  agent: { name: 'PiClaw', avatar: '/fixture/avatar.svg' },
  user: { name: 'Rui', avatar: '/fixture/user.svg' },
  currentSession: 'main',
  sessions: [
    { key: 'main', name: 'Fixture session', parentKey: null, createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-01T12:00:00.000Z', archived: false, pinned: false, running: false, messageCount: 0 },
  ],
  model: { id: 'fixture', provider: 'test', name: 'fixture', reasoning: true, contextWindow: 65536, maxTokens: 8192, thinkingLevels: ['off', 'low', 'medium', 'high'] },
  thinking: 'medium',
  context: { tokens: 0, window: 65536, percent: 0, compactCommand: '/compact' },
  metrics: {
    hostname: 'fixture-host', platform: 'linux', scope: 'server-os', available: true,
    sampled_at: Date.parse('2026-01-01T12:00:00.000Z'), sample_interval_ms: 2000,
    cpu_percent: 25, cpu_series: [10, 15, 25], ram_percent: 50, ram_series: [40, 45, 50],
    ram_total_bytes: 16 * 1024 ** 3, ram_used_bytes: 8 * 1024 ** 3,
    buffer_cache_bytes: 2 * 1024 ** 3, buffer_cache_series_bytes: [1, 1.5, 2].map(n => n * 1024 ** 3),
    process_rss_bytes: 100 * 1024 ** 2, process_rss_series_bytes: [80, 90, 100].map(n => n * 1024 ** 2),
    swap_percent: null, swap_total_bytes: 0, swap_used_bytes: 0, swap_series: [],
    vram_percent: null, vram_total_bytes: 0, vram_used_bytes: 0, vram_series: [],
  },
  plan: {
    sessionKey: 'main', revision: 1,
    markdown: '- [x] Inspect reference\n- [-] Port sidebar\n- [ ] Verify tablet layout\n\nKnown fixture — no model execution.',
  },
  messages: [], queue: [],
  activity: { active: false, turnKey: null, type: null, title: '', thought: '', draft: '' },
  compose: '',
  commands: [{ name: '/model', description: 'Show or set the model' }, { name: '/context', description: 'Show context window usage' }],
  workspace: { entries: [{ name: 'README.md', path: 'README.md', kind: 'file' }] },
  ui: { scenario: 'idle', planOpen: false, populated: false, workspaceOpen: false, composeHeight: 80, metersEnabled: true, metersCollapsed: false, popup: null, hoverMessageId: null },
});

export const fixtureAvatars = deepFreeze({
  '/fixture/avatar.svg': '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" rx="12" fill="#326b82"/></svg>',
  '/fixture/user.svg': '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" rx="12" fill="#9f613f"/></svg>',
});

export const populatedMessages = deepFreeze([
  { id: 101, sessionKey: 'main', role: 'user', at: '2026-01-01T11:58:00.000Z', text: 'Compare the two interfaces.' },
  { id: 102, sessionKey: 'main', role: 'assistant', at: '2026-01-01T11:59:00.000Z', text: '## Visual review\n\nThe **Plan sidebar** is ready for comparison.\n\n- Typography\n- Spacing\n- Controls' },
]);

export function createCaseState(scenario = 'idle') {
  const state = structuredClone(canonicalState);
  const allowed = ['idle', 'plan-open', 'populated', 'populated-plan-open', 'message-hover', 'queued', 'working', 'sessions', 'models', 'quick-actions', 'workspace'];
  if (!allowed.includes(scenario)) throw new Error('Unknown canonical scenario: ' + scenario);
  state.ui.scenario = scenario;
  state.ui.planOpen = ['plan-open', 'populated-plan-open'].includes(scenario);
  state.ui.populated = ['populated', 'populated-plan-open', 'message-hover', 'queued', 'working'].includes(scenario);
  if (state.ui.populated) {
    state.messages = structuredClone(populatedMessages);
    state.sessions[0].messageCount = state.messages.length;
  }
  if (scenario === 'message-hover') state.ui.hoverMessageId = 102;
  if (['queued', 'working'].includes(scenario)) state.queue = [
    { id: 201, sessionKey: 'main', text: 'Queued fixture: inspect the toolbar next.', position: 0, mode: 'queued' },
    { id: 202, sessionKey: 'main', text: 'Second queued fixture: preserve FIFO order.', position: 1, mode: 'queued' },
  ];
  if (scenario === 'working') {
    state.activity = { active: true, turnKey: 'fixture-turn', type: 'tool_use', title: 'Inspecting layout', thought: 'Compare the composer and status surfaces.\nKeep the session state identical.', draft: 'Checking the shared layout.\nThe result will include a screenshot.' };
    state.sessions[0].running = true;
    state.compose = 'Follow up on the spacing';
    state.context = { ...state.context, tokens: 16384, window: 65536, percent: 25 };
  }
  if (['sessions', 'models', 'quick-actions'].includes(scenario)) state.ui.popup = scenario;
  if (['sessions', 'quick-actions'].includes(scenario)) state.sessions.push({ ...state.sessions[0], key: 'research', name: 'Research', parentKey: 'main', messageCount: 0 });
  if (scenario === 'workspace') state.ui.workspaceOpen = true;
  return state;
}
function deepFreeze(value) {
  if (value && typeof value === 'object') { Object.values(value).forEach(deepFreeze); Object.freeze(value); }
  return value;
}
