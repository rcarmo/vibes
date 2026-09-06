"""Pi conversation selection. Caller must own the Pi request lock throughout."""


class PiSessionSelector:
    def __init__(self):
        self.active = 'default'
        self.paths = {}

    async def select(self, chat_id, rpc):
        if not isinstance(chat_id, str) or not chat_id:
            raise ValueError('Chat ID required')
        state = await rpc({'type': 'get_state'})
        if not state or not state.get('success'):
            raise RuntimeError('Unable to inspect Pi session')
        data = state.get('data', {})
        if data.get('isStreaming') or data.get('isCompacting'):
            raise RuntimeError('Pi session is busy')
        current_path = data.get('sessionFile')
        if current_path:
            self.paths[self.active] = current_path
        if chat_id == self.active:
            return current_path
        if not current_path:
            raise RuntimeError('Pi session persistence is required for switching')
        target = self.paths.get(chat_id)
        command = {'type': 'switch_session', 'sessionPath': target} if target else {'type': 'new_session'}
        result = await rpc(command)
        if not result or not result.get('success') or result.get('data', {}).get('cancelled'):
            raise RuntimeError('Pi session switch failed or was cancelled')
        confirmed = await rpc({'type': 'get_state'})
        path = (confirmed or {}).get('data', {}).get('sessionFile')
        if not confirmed or not confirmed.get('success') or not path:
            # Active context is uncertain: do not permit a prompt until caller recovers.
            raise RuntimeError('Unable to confirm selected Pi session')
        if target and path != target:
            raise RuntimeError('Pi selected an unexpected session file')
        self.active = chat_id
        self.paths[chat_id] = path
        return path
