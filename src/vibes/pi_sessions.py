"""Pi conversation selection. Caller must own the Pi request lock throughout."""


class PiSessionSelector:
    def __init__(self):
        self.active = 'default'
        self.paths = {}
        self.uncertain = False

    async def select(self, chat_id, rpc, *, persisted_path=None):
        if self.uncertain:
            raise RuntimeError('Pi session state is uncertain; restart/recovery required')
        if not isinstance(chat_id, str) or not chat_id:
            raise ValueError('Chat ID required')
        state = await rpc({'type': 'get_state'})
        if not state or not state.get('success'):
            raise RuntimeError('Unable to inspect Pi session')
        data = state.get('data', {})
        if data.get('isStreaming') or data.get('isCompacting'):
            raise RuntimeError('Pi session is busy')
        current_path = data.get('sessionFile')
        if persisted_path is not None and (not isinstance(persisted_path, str) or not persisted_path):
            raise ValueError('Invalid persisted Pi session path')
        if current_path:
            self.paths[self.active] = current_path
        if persisted_path:
            self.paths[chat_id] = persisted_path
        if chat_id == self.active and (not persisted_path or persisted_path == current_path):
            return current_path
        if not current_path:
            raise RuntimeError('Pi session persistence is required for switching')
        target = self.paths.get(chat_id)
        command = {'type': 'switch_session', 'sessionPath': target} if target else {'type': 'new_session'}
        self.uncertain = True
        result = await rpc(command)
        if result and result.get('success') and result.get('data', {}).get('cancelled'):
            self.uncertain = False
            raise RuntimeError('Pi session switch was cancelled')
        if not result or not result.get('success'):
            raise RuntimeError('Pi session switch failed')
        confirmed = await rpc({'type': 'get_state'})
        path = (confirmed or {}).get('data', {}).get('sessionFile')
        if not confirmed or not confirmed.get('success') or not path:
            # Active context is uncertain: do not permit a prompt until caller recovers.
            raise RuntimeError('Unable to confirm selected Pi session')
        if target and path != target:
            raise RuntimeError('Pi selected an unexpected session file')
        self.active = chat_id
        self.paths[chat_id] = path
        self.uncertain = False
        return path
