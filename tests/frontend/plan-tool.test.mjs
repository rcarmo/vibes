import { test, expect } from 'bun:test';
// Transpile only the registration adapter; schema builders and fetch are test seams.
// Actual Pi-loaded model execution is verified by the isolated live roundtrip.
const path = new URL('../../src/vibes/extensions/pi-vibes-tools.ts', import.meta.url);
const code = await Bun.file(path).text();
const javascript = new Bun.Transpiler({ loader: 'ts' }).transformSync(code.replace('import { Type } from "@sinclair/typebox";', 'const Type = globalThis.__planTestType;'));

test('Pi Plan serializes action fields only when provider materializes unused optional values', async () => {
    const originalFetch = globalThis.fetch, originalType = globalThis.__planTestType;
    const oldUrl = process.env.VIBES_PI_TOOLS_URL, oldToken = process.env.VIBES_ATTACHMENT_TOKEN;
    globalThis.__planTestType = new Proxy({}, { get: (_, key) => (...args) => ({ type: key, args }) });
    const tools = [], requests = [];
    process.env.VIBES_PI_TOOLS_URL = 'http://127.0.0.1:1';
    process.env.VIBES_ATTACHMENT_TOKEN = 'synthetic-test-token';
    globalThis.fetch = async (url, options) => {
        requests.push({ path: url.pathname, ...options, body: JSON.parse(options.body) });
        return new Response(JSON.stringify({ markdown: '', revision: 0 }));
    };
    try {
        const { default: register } = await import('data:text/javascript;base64,' + Buffer.from(javascript).toString('base64'));
        register({ registerTool: tool => tools.push(tool) });
        const tool = tools.find(tool => tool.name === 'vibes_plan');
        expect(tool).toBeDefined();
        const empty = { markdown: '', plan: [], patches: [], edits: [] };
        await tool.execute('read', { action: 'read', ...empty });
        expect(requests[0].body).toEqual({ action: 'read' });
        const controller = new AbortController();
        await tool.execute('write', { action: 'write', expected_revision: 0, ...empty, markdown: '- [ ] New' }, controller.signal);
        expect(requests[1].body).toEqual({ action: 'write', expected_revision: 0, markdown: '- [ ] New' });
        expect(requests[1].signal).toBe(controller.signal);
        expect(requests[1].path).toBe('/internal/agent-tools/plan');
    } finally {
        globalThis.fetch = originalFetch;
        if (originalType === undefined) delete globalThis.__planTestType; else globalThis.__planTestType = originalType;
        if (oldUrl === undefined) delete process.env.VIBES_PI_TOOLS_URL; else process.env.VIBES_PI_TOOLS_URL = oldUrl;
        if (oldToken === undefined) delete process.env.VIBES_ATTACHMENT_TOKEN; else process.env.VIBES_ATTACHMENT_TOKEN = oldToken;
    }
});
