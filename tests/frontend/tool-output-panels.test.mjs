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

test('completed latest call does not stop another running tool timer', async () => {
    const { hasRunningTool } = await import('../../src/vibes/static/js/components/tool-output-panels.js');
    expect(hasRunningTool({ status: 'completed', tool_calls: [{ started_at: 1, status: 'running' }, { started_at: 2, ended_at: 3, status: 'completed' }] })).toBe(true);
    expect(hasRunningTool({ tool_calls: [{ started_at: 1, ended_at: 3, status: 'completed' }] })).toBe(false);
});

test('progress-only calls remain visible without fabricating output', () => {
    const panels = toolOutputPanels({ tool_calls: [{ tool_call_id: 'p', output: '', progress_message: '<working>', progress_truncated: true }] });
    expect(panels).toHaveLength(1);
    expect(panels[0].output).toBe('');
    expect(panels[0].progress_message).toBe('<working>');
    expect(panels[0].progress_truncated).toBe(true);
});
