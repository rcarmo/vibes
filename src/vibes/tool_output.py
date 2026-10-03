"""Bounded per-call output state for live status and reconnect snapshots."""
import time


class ToolOutputState:
    def __init__(self, limit=16000):
        self.limit = limit
        self.calls = {}

    def update(self, event):
        call_id = event.get('tool_call_id')
        if not isinstance(call_id, str) or not call_id:
            return event
        if call_id not in self.calls:
            if len(self.calls) >= 256:
                return event
            self.calls[call_id] = {'output': '', 'started_at': time.time(), 'output_truncated': False}
        state = self.calls[call_id]
        if event.get('type') == 'tool_output':
            content = event.get('content', '')
            if isinstance(content, str):
                if event.get('progress'):
                    state['progress_message'] = content[:self.limit]
                else:
                    combined = state['output'] + content
                    state['output'] = combined[-self.limit:]
                    state['output_truncated'] |= len(combined) > self.limit or bool(event.get('content_truncated'))
        return {**event, **state}
