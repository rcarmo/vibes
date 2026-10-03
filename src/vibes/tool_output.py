"""Bounded per-call output state for live status and reconnect snapshots."""
import time


class ToolOutputState:
    def __init__(self, limit=16000):
        self.limit = limit
        self.calls = {}

    def update(self, event):
        call_id = event.get('tool_call_id')
        if not isinstance(call_id, str) or not call_id:
            return {**event, 'tool_calls': self.snapshot()} if self.calls else event
        if call_id not in self.calls:
            if len(self.calls) >= 256:
                return event
            self.calls[call_id] = {'output': '', 'started_at': time.time(), 'output_truncated': False}
        state = self.calls[call_id]
        for field in ('title', 'status'):
            value = event.get(field)
            if isinstance(value, str):
                state[field] = value[:256]
        if event.get('type') == 'tool_output':
            content = event.get('content', '')
            if isinstance(content, str):
                if event.get('progress'):
                    state['progress_message'] = content[:self.limit]
                else:
                    combined = state['output'] + content
                    state['output'] = combined[-self.limit:]
                    state['output_truncated'] |= len(combined) > self.limit or bool(event.get('content_truncated'))
        if event.get('type') == 'tool_status' and event.get('status') in {'completed', 'failed', 'ended'}:
            state.setdefault('ended_at', time.time())
        return {**event, **state, 'tool_calls': self.snapshot()}

    def snapshot(self):
        # Keep aggregate reconnect payload below 64 KiB of output text.
        remaining = 64000
        rows = []
        for call_id, state in reversed(list(self.calls.items())):
            output = state['output'][-min(remaining, self.limit):] if remaining else ''
            remaining -= len(output)
            progress = state.get('progress_message', '')[:remaining]
            remaining -= len(progress)
            rows.append({**state, 'tool_call_id': call_id, 'output': output,
                         'progress_message': progress,
                         'progress_truncated': len(progress) < len(state.get('progress_message', '')),
                         'output_truncated': state['output_truncated'] or len(output) < len(state['output'])})
        return list(reversed(rows))
