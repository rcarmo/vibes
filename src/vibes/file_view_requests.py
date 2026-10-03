"""Bounded browser acknowledgements, scoped to the requesting chat and turn."""
import asyncio
from uuid import uuid4


class FileViewRequests:
    def __init__(self, limit=32):
        self.limit = limit
        self.pending = {}

    async def request(self, session_id, path, owner_check, publish, timeout=15):
        owner_check()
        if len(self.pending) >= self.limit:
            raise ValueError('Too many pending file-view requests')
        request_id = uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = (session_id, future, owner_check)
        try:
            await publish('workspace_view_request', {'request_id': request_id, 'session_id': session_id, 'path': path})
            try:
                result = await asyncio.wait_for(future, timeout)
            except asyncio.TimeoutError:
                return {'request_id': request_id, 'status': 'unacknowledged'}
            owner_check()
            return {'request_id': request_id, 'status': result}
        finally:
            self.pending.pop(request_id, None)

    def acknowledge(self, request_id, session_id, status):
        if status not in {'opened', 'rejected'}:
            raise ValueError('Invalid file-view acknowledgement')
        entry = self.pending.get(request_id)
        if not entry or entry[0] != session_id:
            raise LookupError('No matching file-view request')
        entry[2]()
        if entry[1].done():
            raise LookupError('File-view request already settled')
        entry[1].set_result(status)
