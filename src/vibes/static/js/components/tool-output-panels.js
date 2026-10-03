export function toolOutputPanels(status) {
    const calls = Array.isArray(status?.tool_calls) ? status.tool_calls.slice(-256) : [status];
    return calls.filter(call => call && typeof call.output === 'string' && call.output.length)
        .map(call => ({ ...call, panelKey: `output:${call.tool_call_id || 'current'}` }));
}
