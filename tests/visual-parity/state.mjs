// Shared semantic fixture. Adapters translate only wire formats, never layouts.
export const state = {
  now: '2026-09-15T12:00:00.000Z',
  agent: { name: 'Fixture', avatar: '/fixture/avatar.svg' },
  user: { name: 'Rui', avatar: '/fixture/user.svg' },
  model: { id: 'fixture-model', name: 'fixture-model', provider: 'fixture', reasoning: true, contextWindow: 65536, maxTokens: 8192 },
  thinking: 'medium', context: { tokens: 16384, window: 65536, percent: 25 },
  sessions: [{ id: 'default', name: 'Main' }, { id: 'research', name: 'Research' }],
  messages: [
    { id: 101, role: 'user', at: '2026-09-15T11:58:00.000Z', text: 'Please check the layout and attach the result.' },
    { id: 102, role: 'assistant', at: '2026-09-15T11:59:00.000Z', text: '## Layout check\n\nThe fixture includes **bold text**, *emphasis*, and a [reference](https://example.invalid/).\n\n> Same content, same viewport, different renderers.\n\n```js\nconst ready = true;\n```\n\n- Check spacing\n- Preserve keyboard access' },
  ],
  draft: 'Checking the shared layout.\nThe result will include a screenshot.',
  thought: 'Compare the composer and status surfaces.\nKeep the session state identical.',
  status: 'Inspecting layout',
  compose: 'Follow up on the spacing',
  queue: 'Also check the mobile layout.',
  commands: [{ name: '/model', description: 'Show or set the model' }, { name: '/context', description: 'Show context window usage' }],
};
export const scenarios = ['idle', 'working', 'sessions', 'models', 'quick-actions', 'attachment'];
export const viewports = { desktop: { width: 1440, height: 900 }, tablet: { width: 1024, height: 768 }, mobile: { width: 390, height: 844 } };
export function metrics() {
  return { hostname: 'fixture-host', platform: 'linux', scope: 'server-os', available: true,
    sampled_at: Date.parse(state.now), sample_interval_ms: 2000,
    cpu_percent: 25, cpu_series: [10, 20, 40, 20, 25], ram_percent: 50, ram_series: [42, 44, 48, 49, 50],
    ram_total_bytes: 16 * 1024 ** 3, ram_used_bytes: 8 * 1024 ** 3,
    buffer_cache_bytes: 2 * 1024 ** 3, buffer_cache_series_bytes: [1, 1.5, 2].map(n=>n*1024**3),
    process_rss_bytes: 128 * 1024 ** 2, process_rss_series_bytes: [100, 120, 128].map(n=>n*1024**2),
    process_memory: { rss_bytes: 128 * 1024 ** 2, vm_rss_bytes: 128 * 1024 ** 2 },
    swap_percent: null, swap_total_bytes: 0, swap_used_bytes: 0, swap_series: [], vram_percent: null, vram_series: [], vram_total_bytes: 0 };
}
