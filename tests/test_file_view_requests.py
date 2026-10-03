import asyncio
import pytest
from vibes.file_view_requests import FileViewRequests


@pytest.mark.asyncio
async def test_file_view_requires_matching_ack_and_live_owner():
    manager = FileViewRequests()
    events = []
    alive = True
    def check():
        if not alive:
            raise PermissionError('expired turn')
    async def publish(kind, data):
        events.append(data)
    task = asyncio.create_task(manager.request('chat-a', 'note.txt', check, publish))
    await asyncio.sleep(0)
    request_id = events[0]['request_id']
    with pytest.raises(LookupError):
        manager.acknowledge(request_id, 'chat-b', 'opened')
    manager.acknowledge(request_id, 'chat-a', 'opened')
    assert (await task)['status'] == 'opened'
    assert not manager.pending
    task = asyncio.create_task(manager.request('chat-a', 'note.txt', check, publish))
    await asyncio.sleep(0)
    alive = False
    with pytest.raises(PermissionError):
        manager.acknowledge(events[-1]['request_id'], 'chat-a', 'opened')
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not manager.pending


@pytest.mark.asyncio
async def test_missing_browser_ack_is_not_success():
    manager = FileViewRequests()
    async def publish(kind, data):
        pass
    result = await manager.request('chat', 'note.txt', lambda: None, publish, timeout=0.001)
    assert result['status'] == 'unacknowledged'
    assert not manager.pending
