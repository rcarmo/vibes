import { expect, test } from 'bun:test';

const source = await Bun.file(new URL('../src/vibes/extensions/pi-vibes-tools.ts', import.meta.url)).text();
const js = new Bun.Transpiler({ loader: 'ts' }).transformSync(source)
  .replace(/^import .*$/gm, '').replace('export default function', 'return function');
const Type = new Proxy({}, { get: (_, key) => key === 'Object' ? (value) => value : () => ({}) });

test('Pi widget forwards only supplied fields, fixes request identity and returns no HTML', async () => {
  const tools = new Map();
  new Function('Type', js)(Type)({ registerTool(tool) { tools.set(tool.name, tool); } });
  const originalFetch = globalThis.fetch;
  const base = process.env.VIBES_PI_TOOLS_URL;
  const token = process.env.VIBES_ATTACHMENT_TOKEN;
  process.env.VIBES_PI_TOOLS_URL = 'http://127.0.0.1:1234';
  process.env.VIBES_ATTACHMENT_TOKEN = 'fixture';
  try {
    let body;
    const signal = new AbortController().signal;
    globalThis.fetch = async (url, options) => {
      expect(new URL(url).pathname).toBe('/internal/agent-tools/dashboard-widget');
      expect(options.signal).toBe(signal);
      body = JSON.parse(options.body);
      return { ok: true, json: async () => ({ widget_id: 'fixture-id', message_id: 1, session_id: 'default' }) };
    };
    const result = await tools.get('send_dashboard_widget').execute('stable-call', {
      html: '<p>Fixture</p>', title: null, description: undefined, interactive: false,
    }, signal);
    expect(body).toEqual({ html: '<p>Fixture</p>', interactive: false, request_id: 'stable-call' });
    expect(JSON.stringify(result)).not.toContain('<p>');
    expect(result.details.widget.widget_id).toBe('fixture-id');
    globalThis.fetch = async () => ({ ok: false });
    await expect(tools.get('send_dashboard_widget').execute('fail', { html: 'x' }, signal)).rejects.toThrow('Widget delivery failed');
  } finally {
    globalThis.fetch = originalFetch;
    if (base === undefined) delete process.env.VIBES_PI_TOOLS_URL; else process.env.VIBES_PI_TOOLS_URL = base;
    if (token === undefined) delete process.env.VIBES_ATTACHMENT_TOKEN; else process.env.VIBES_ATTACHMENT_TOKEN = token;
  }
});
