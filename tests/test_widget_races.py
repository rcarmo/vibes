"""Force commit-boundary races; no browser events or orphan artifacts may escape."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes import agent_attachments
from vibes.routes import widgets


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_task', [False, True])
async def test_widget_commit_cancellation_compensates_before_artifact_read(db, monkeypatch, cancel_task):
    monkeypatch.setattr(widgets, 'get_db', AsyncMock(return_value=db))
    broadcast = AsyncMock()
    monkeypatch.setattr(widgets, 'broadcast_event', broadcast)
    root = await db.create_interaction({'type': 'user', 'content': 'race'})
    owner = {'mode': 'pi', 'session_id': 'default', 'agent_id': 'pi', 'thread_id': root,
             'turn_id': 'race-turn', 'cancelled': False}
    agent_attachments.set_active(owner)
    started, release = asyncio.Event(), asyncio.Event()
    original_commit = db._connection.commit
    commits = 0

    async def delayed_commit():
        nonlocal commits
        commits += 1
        if commits == 1:
            started.set()
            await release.wait()
        await original_commit()

    monkeypatch.setattr(db._connection, 'commit', delayed_commit)
    fixed_id = 'a' * 32
    from types import SimpleNamespace
    monkeypatch.setattr(widgets.uuid, 'uuid4', lambda: SimpleNamespace(hex=fixed_id))
    app = web.Application()
    widgets.setup_routes(app)
    pending = None
    try:
        async with TestClient(TestServer(app)) as client:
            pending = asyncio.create_task(widgets.publish_widget('pi', 'default', {
                'html': '<p>must disappear</p>', 'request_id': 'race',
            }, expected=owner))
            await asyncio.wait_for(started.wait(), 2)
            lookup = asyncio.create_task(client.get(f'/api/sessions/default/widgets/{fixed_id}'))
            await asyncio.sleep(.02)
            assert not lookup.done()  # Shared connection must not leak the uncommitted row.
            if cancel_task:
                pending.cancel()
            else:
                owner['cancelled'] = True
            release.set()
            with pytest.raises(asyncio.CancelledError if cancel_task else PermissionError):
                await pending
            response = await asyncio.wait_for(lookup, 2)
            assert response.status == 404
            assert owner.get('widget_receipts') == {}
            broadcast.assert_not_awaited()
            async with db._connection.execute("SELECT COUNT(*) AS n FROM interactions WHERE type='agent_response'") as cursor:
                assert (await cursor.fetchone())['n'] == 0
    finally:
        release.set()
        if pending and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        agent_attachments.clear_active(owner)
