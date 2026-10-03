"""Sanitised native task records; task IDs are never chat destinations."""
import math


def normalise_task_event(kind, data):
    states = {'subagent.started': 'running', 'subagent.completed': 'completed', 'subagent.failed': 'failed'}
    if kind not in states or not isinstance(data, dict):
        return None
    task_id = data.get('toolCallId', data.get('tool_call_id'))
    if not isinstance(task_id, str) or not task_id or len(task_id) > 256 or any(ord(char) < 32 or ord(char) == 127 for char in task_id):
        return None
    result = {'kind': 'native_task', 'task_id': task_id, 'status': states[kind]}
    name = data.get('agentDisplayName', data.get('agent_display_name', data.get('agentName', data.get('agent_name'))))
    if isinstance(name, str) and len(name) <= 256 and not any(ord(char) < 32 or ord(char) == 127 for char in name):
        result['name'] = name
    for source, target in [('duration', 'duration_ms'), ('totalTokens', 'total_tokens'), ('totalToolCalls', 'total_tool_calls')]:
        value = data.get('durationMs', data.get('duration')) if source == 'duration' else data.get(source, data.get({'totalTokens': 'total_tokens', 'totalToolCalls': 'total_tool_calls'}[source]))
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 10**12:
            result[target] = value
    # Raw error/provider fields are private diagnostics, not public task labels.
    return result
