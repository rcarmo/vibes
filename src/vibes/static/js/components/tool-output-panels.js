export function hasRunningTool(status) {
    const calls = Array.isArray(status?.tool_calls) ? status.tool_calls : [status];
    return calls.some(call => call?.started_at && !call.ended_at && !['completed', 'failed', 'ended'].includes(call.status));
}

export function toolOutputPanels(status) {
    const calls = Array.isArray(status?.tool_calls) ? status.tool_calls.slice(-256) : [status];
    return calls.filter(call => call && (
        (typeof call.output === 'string' && call.output.length) ||
        (typeof call.progress_message === 'string' && call.progress_message.length)))
        .map(call => ({ ...call, panelKey: `output:${call.tool_call_id || 'current'}` }));
}
