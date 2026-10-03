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

@pytest.mark.asyncio
async def test_rejected_and_duplicate_file_view_acknowledgements():
    manager = FileViewRequests()
    events = []
    async def publish(kind, data):
        events.append(data)
    task = asyncio.create_task(manager.request('chat', 'a.txt', lambda: None, publish))
    await asyncio.sleep(0)
    request_id = events[0]['request_id']
    with pytest.raises(ValueError):
        manager.acknowledge(request_id, 'chat', 'pretend-success')
    manager.acknowledge(request_id, 'chat', 'rejected')
    with pytest.raises(LookupError):
        manager.acknowledge(request_id, 'chat', 'opened')
    assert (await task)['status'] == 'rejected'
    with pytest.raises(LookupError):
        manager.acknowledge(request_id, 'chat', 'opened')


@pytest.mark.asyncio
async def test_pending_view_request_limit_does_not_evict_owned_work():
    manager = FileViewRequests(limit=1)
    async def publish(kind, data):
        pass
    first = asyncio.create_task(manager.request('a', 'a.txt', lambda: None, publish))
    await asyncio.sleep(0)
    with pytest.raises(ValueError, match='Too many'):
        await manager.request('b', 'b.txt', lambda: None, publish)
    assert len(manager.pending) == 1
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first


@pytest.mark.asyncio
async def test_publish_failure_releases_capacity_without_opened_claim():
    from unittest.mock import AsyncMock
    requests = FileViewRequests(limit=1)
    publish = AsyncMock(side_effect=RuntimeError('transport unavailable'))
    with pytest.raises(RuntimeError, match='transport unavailable'):
        await requests.request('chat', 'file.txt', lambda: True, publish)
    assert requests.pending == {}
    events = []
    async def acknowledge_publish(kind, data):
        events.append(data)
        requests.acknowledge(data['request_id'], 'chat', 'rejected')
    result = await requests.request('chat', 'next.txt', lambda: True, acknowledge_publish)
    assert result['status'] == 'rejected'
    assert len(events) == 1
