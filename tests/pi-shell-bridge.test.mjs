import { expect, test } from 'bun:test';

// Adapter test only; no shared frontend, provider call or runtime installation.
const source = await Bun.file(new URL('../src/vibes/extensions/pi-vibes-tools.ts', import.meta.url)).text();
const js = new Bun.Transpiler({ loader: 'ts' }).transformSync(source)
  .replace(/^import .*$/gm, '').replace('export default function', 'return function');
const scalar = () => ({});
const Type = new Proxy({}, { get: (_, key) => key === 'Object' ? (value) => value : scalar });

function bashTool() {
  const tools = new Map();
  new Function('Type', js)(Type)({ registerTool(tool) { tools.set(tool.name, tool); } });
  return tools.get('bash');
}

async function withBridge(run) {
  const originalFetch = globalThis.fetch;
  const base = process.env.VIBES_PI_TOOLS_URL;
  const token = process.env.VIBES_ATTACHMENT_TOKEN;
  process.env.VIBES_PI_TOOLS_URL = 'http://127.0.0.1:1234';
  process.env.VIBES_ATTACHMENT_TOKEN = 'fixture';
  try { await run(); }
  finally {
    globalThis.fetch = originalFetch;
    if (base === undefined) delete process.env.VIBES_PI_TOOLS_URL; else process.env.VIBES_PI_TOOLS_URL = base;
    if (token === undefined) delete process.env.VIBES_ATTACHMENT_TOKEN; else process.env.VIBES_ATTACHMENT_TOKEN = token;
  }
}

test('Pi bash routes command and optional timeout through the scoped Python runner', async () => {
  await withBridge(async () => {
    const calls = [];
    globalThis.fetch = async (url, options) => {
      calls.push({ path: new URL(url).pathname, options, body: JSON.parse(options.body) });
      return { ok: true, json: async () => ({ stdout: 'expected output', exit_code: 0,
        env: { NEVER_EXPORT: 'private' }, command: 'secret-bearing preparation' }) };
    };
    const signal = new AbortController().signal;
    const tool = bashTool();
    const result = await tool.execute('one', { command: 'echo expected', timeout: null }, signal);
    expect(calls[0].path).toBe('/internal/agent-tools/shell');
    expect(calls[0].body).toEqual({ command: 'echo expected' });
    expect(calls[0].options.signal).toBe(signal);
    expect(result).toEqual({ content: [{ type: 'text', text: 'expected output' }], details: { exit_code: 0 }, isError: false });
    expect(JSON.stringify(result)).not.toContain('private');
    await tool.execute('two', { command: 'false', timeout: 12 }, signal);
    expect(calls[1].body).toEqual({ command: 'false', timeout: 12 });
  });
});

test('Pi bash preserves nonzero status, uses no local fallback and hides server errors', async () => {
  await withBridge(async () => {
    const tool = bashTool();
    globalThis.fetch = async () => ({ ok: true, json: async () => ({ stdout: '', exit_code: 7 }) });
    const result = await tool.execute('one', { command: 'exit 7' });
    expect(result.isError).toBe(true);
    expect(result.details).toEqual({ exit_code: 7 });
    globalThis.fetch = async () => ({ ok: false, json: async () => ({ error: 'private credential' }) });
    await expect(tool.execute('two', { command: 'false' })).rejects.toThrow('Vibes shell execution failed');
    globalThis.fetch = async (_url, options) => { throw options.signal.reason; };
    const controller = new AbortController();
    controller.abort(new Error('cancelled fixture'));
    await expect(tool.execute('three', { command: 'sleep 60' }, controller.signal)).rejects.toThrow('cancelled fixture');
  });
});
