"""Receipt recovery survives mutable state and cancellation boundaries."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request, TestClient, TestServer

from vibes.routes import classic, agents
from vibes.sessions import SessionStore


async def client_for(db, monkeypatch, enqueue):
    monkeypatch.setattr(classic, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda _: 'pi')
    monkeypatch.setattr(agents, '_is_agent_busy', lambda _: False)
    monkeypatch.setattr(agents, 'broadcast_event', AsyncMock())
    monkeypatch.setattr(agents, 'queue_link_preview_fetch', lambda *args: None)
    monkeypatch.setattr(agents, 'enqueue', enqueue)
    app = web.Application()
    classic.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


@pytest.mark.asyncio
async def test_confirmed_retry_survives_parent_expiry_media_delete_and_archive(db, monkeypatch):
    enqueue = Mock(return_value=True)
    client = await client_for(db, monkeypatch, enqueue)
    session = await SessionStore(db).create('Receipt longevity')
    key = session['id']
    root = await db.create_interaction({'type':'user','content':'parent','session_id':key})
    await db.begin_turn('parent', root, 'default')
    media = await db.create_media('own.txt','text/plain',b'own',metadata={'session_id':key})
    body = {'prompt':'one admission','parent_turn_id':'parent','media':[{'media_id':media,'session_id':key}], 'client_request_id':'once'}
    try:
        response = await client.post(f'/api/sessions/{key}/prompt',json=body)
        assert response.status == 201
        result = await response.json()
        await db.end_turn('parent')
        await db.delete_media([media])
        await SessionStore(db).update(key,archived=True)
        repeated = await client.post(f'/api/sessions/{key}/prompt',json=body)
        assert repeated.status == 201 and await repeated.json() == result
        enqueue.assert_called_once()
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('point', ['claim','finalize'])
async def test_cancel_at_claim_or_terminal_commit_preserves_no_replay(db, monkeypatch, point):
    enqueue = Mock(return_value=True)
    client = await client_for(db, monkeypatch, enqueue)
    request = make_mocked_request('POST','/api/sessions/default/prompt',match_info={'id':'default'})
    request.json = AsyncMock(return_value={'prompt':'cancel boundary','client_request_id':point})
    if point == 'claim':
        original = classic._claim
        async def boundary(*args):
            value = await original(*args)
            # Cancellation targets the request, not the shielded ownership claim.
            owner.cancel()
            return value
        monkeypatch.setattr(classic,'_claim',boundary)
    else:
        original = classic._finalize
        async def boundary(*args):
            await original(*args)
            if args[3] == 'confirmed':
                raise asyncio.CancelledError()
        monkeypatch.setattr(classic,'_finalize',boundary)
    owner = asyncio.create_task(classic.prompt(request))
    try:
        with pytest.raises(asyncio.CancelledError):
            await owner
        receipt = await classic._receipt(db,'default',point)
        assert receipt['state'] == ('uncertain' if point == 'claim' else 'confirmed')
        response = await client.post('/api/sessions/default/prompt',json={'prompt':'cancel boundary','client_request_id':point})
        assert response.status == (409 if point == 'claim' else 201)
        assert enqueue.call_count == (0 if point == 'claim' else 1)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_reserved_turn_id_is_the_actual_worker_identity(db, monkeypatch):
    jobs = []
    def enqueue(function,*args,**kwargs):
        jobs.append((function,args,kwargs))
        return True
    client = await client_for(db,monkeypatch,enqueue)
    observed = []
    original_begin = db.begin_turn
    async def begin(turn_id,*args):
        observed.append(turn_id)
        return await original_begin(turn_id,*args)
    monkeypatch.setattr(db,'begin_turn',begin)
    monkeypatch.setattr(agents,'_dispatch_pi_thread',AsyncMock(return_value={'text':'reply','content':[]}))
    try:
        response = await client.post('/api/sessions/default/prompt',json={'prompt':'worker turn','client_request_id':'worker'})
        result = await response.json()
        function,args,kwargs = jobs[0]
        await function(*args,**kwargs)
        assert observed == [result['turn_id']]
    finally:
        await client.close()
