"""Bounded per-call output state for live status and reconnect snapshots."""
import time


class ToolOutputState:
    def __init__(self, limit=16000):
        self.limit = limit
        self.calls = {}
        self.calls_truncated = False

    def update(self, event):
        call_id = event.get('tool_call_id')
        if not isinstance(call_id, str) or not call_id:
            return {**event, 'tool_calls': self.snapshot(), 'tool_calls_truncated': self.calls_truncated} if self.calls else event
        if call_id not in self.calls:
            if len(self.calls) >= 256:
                self.calls_truncated = True
                return {**event, 'tool_calls': self.snapshot(), 'tool_calls_truncated': True}
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
                    state['progress_truncated'] = len(content) > self.limit or bool(event.get('content_truncated'))
                else:
                    combined = content if event.get('replace_output') else state['output'] + content
                    state['output'] = combined[-self.limit:]
                    truncated = len(combined) > self.limit or bool(event.get('content_truncated'))
                    state['output_truncated'] = truncated if event.get('replace_output') else state['output_truncated'] or truncated
        if event.get('type') == 'tool_status' and event.get('status') in {'completed', 'failed', 'ended'}:
            state.setdefault('ended_at', time.time())
        return {**event, **state, 'tool_calls': self.snapshot(), 'tool_calls_truncated': self.calls_truncated}

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
                         'progress_truncated': state.get('progress_truncated', False) or len(progress) < len(state.get('progress_message', '')),
                         'output_truncated': state['output_truncated'] or len(output) < len(state['output'])})
        return list(reversed(rows))
