import { test, expect } from 'bun:test';
import { toolOutputPanels } from '../../src/vibes/static/js/components/tool-output-panels.js';
test('reconnect collection uses durable per-call disclosure keys', () => {
    const panels = toolOutputPanels({ type: 'writing', tool_calls: [{ tool_call_id: 'a', output: '<unsafe>' }, { tool_call_id: 'b', output: 'second' }] });
    expect(panels.map(row => row.panelKey)).toEqual(['output:a', 'output:b']);
    expect(panels[0].output).toBe('<unsafe>');
});
test('empty output is omitted and legacy current output remains usable', () => {
    expect(toolOutputPanels({ tool_calls: [{ output: '' }] })).toEqual([]);
    expect(toolOutputPanels({ output: 'legacy' })[0].panelKey).toBe('output:current');
});
