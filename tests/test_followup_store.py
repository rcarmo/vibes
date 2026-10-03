import pytest
from vibes.db import Database
from vibes.followup_store import FollowupStore


@pytest.mark.asyncio
async def test_claim_priority_release_and_stale_owner_rejection(db):
    store = FollowupStore(db)
    queued = await store.enqueue(thread_id=1, agent_id='pi', message_id=1, content='normal')
    steer = await store.enqueue(thread_id=1, agent_id='pi', message_id=2, content='steer', steer=True)
    first = await store.claim(1, 'pi')
    assert first['row_id'] == steer['row_id']
    await store.transition_claim(first)
    second = await store.claim(1, 'pi')
    assert second['row_id'] == first['row_id']
    assert second['claim_token'] != first['claim_token']
    with pytest.raises(ValueError, match='no longer owned'):
        await store.transition_claim(first, admitted=True)
    await store.transition_claim(second, admitted=True)
    assert (await store.claim(1, 'pi'))['row_id'] == queued['row_id']
    assert all('claim_token' not in item for item in await store.list(thread_id=1, agent_id='pi'))


@pytest.mark.asyncio
async def test_restart_retains_pending_and_never_replays_claimed_or_admitted(tmp_path):
    db = Database(str(tmp_path / 'queue.db'))
    await db.connect()
    try:
        store = FollowupStore(db)
        rows = [await store.enqueue(thread_id=1, agent_id='pi', message_id=i, content=str(i)) for i in range(3)]
        first = await store.claim(1, 'pi')
        await store.transition_claim(first, admitted=True)
        await store.claim(1, 'pi')
        await db.close()
        await db.connect()
        store = FollowupStore(db)
        await store.recover()
        await store.recover()
        recovered = await store.list(thread_id=1, agent_id='pi')
        assert [item['state'] for item in recovered] == ['uncertain', 'uncertain', 'pending']
        assert [item['row_id'] for item in recovered] == [item['row_id'] for item in rows]
        assert (await store.claim(1, 'pi'))['row_id'] == rows[2]['row_id']
        assert await store.claim(1, 'pi') is None
        new = await store.enqueue(thread_id=1, agent_id='pi', message_id=4, content='new')
        assert new['row_id'] < rows[-1]['row_id']
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_mutations_are_scoped_pending_only_and_ids_never_reused(db):
    store = FollowupStore(db)
    rows = [await store.enqueue(thread_id=1, agent_id='pi', message_id=i, content=str(i)) for i in range(3)]
    assert not await store.reorder(rows[1]['row_id'], 'down', thread_id=2, agent_id='pi')
    assert await store.remove(rows[1]['row_id'], thread_id=1, agent_id='acp') is None
    assert await store.reorder(rows[1]['row_id'], 'down', thread_id=1, agent_id='pi')
    listing = await store.list(thread_id=1, agent_id='pi')
    assert [row['row_id'] for row in listing] == [rows[i]['row_id'] for i in (0, 2, 1)]
    claim = await store.claim(1, 'pi')
    assert await store.remove(claim['row_id'], thread_id=1, agent_id='pi') is None
    assert not await store.reorder(claim['row_id'], 'down', thread_id=1, agent_id='pi')
    await store.recover()
    assert await store.remove(claim['row_id'], thread_id=1, agent_id='pi') is None
    for row in rows[1:]:
        assert (await store.remove(row['row_id'], thread_id=1, agent_id='pi'))['row_id'] == row['row_id']
    new = await store.enqueue(thread_id=1, agent_id='pi', message_id=9, content='new')
    assert new['row_id'] < rows[-1]['row_id']
    for invalid in (True, 0, 1, '1', -1.0):
        with pytest.raises(ValueError):
            await store.remove(invalid, thread_id=1, agent_id='pi')


@pytest.mark.asyncio
async def test_steering_claim_preserves_identity_order_and_transfers_priority(db):
    store = FollowupStore(db)
    rows = [await store.enqueue(thread_id=1, agent_id='pi', message_id=i, content=str(i)) for i in range(3)]
    assert await store.claim_for_steer(rows[1]['row_id'], thread_id=2, agent_id='pi') is None
    claim = await store.claim_for_steer(rows[1]['row_id'], thread_id=1, agent_id='pi')
    assert await store.claim_for_steer(rows[1]['row_id'], thread_id=1, agent_id='pi') is None
    await store.transition_claim(claim)
    assert [item['row_id'] for item in await store.list(thread_id=1, agent_id='pi')] == [item['row_id'] for item in rows]
    old_steer = await store.enqueue(thread_id=1, agent_id='pi', message_id=9, content='old steer', steer=True)
    claim = await store.claim_for_steer(rows[1]['row_id'], thread_id=1, agent_id='pi')
    await store.transition_claim(claim, defer_steer=True)
    assert (await store.claim(1, 'pi'))['row_id'] == old_steer['row_id']
    promoted = await store.claim(1, 'pi')
    assert promoted['row_id'] == rows[1]['row_id']
    assert promoted['mode'] == 'steer' and promoted['emulated'] is True
    await store.transition_claim(promoted, admitted=True)
    assert (await store.claim(1, 'pi'))['row_id'] == rows[0]['row_id']
    with pytest.raises(ValueError, match='no longer owned'):
        await store.transition_claim(claim)


@pytest.mark.asyncio
async def test_independent_connections_cannot_both_claim_same_row(tmp_path):
    import asyncio
    path = str(tmp_path / 'claims.db')
    first, second = Database(path), Database(path)
    await first.connect()
    await second.connect()
    try:
        stores = [FollowupStore(first), FollowupStore(second)]
        row = await stores[0].enqueue(thread_id=1, agent_id='pi', message_id=1, content='once')
        claims = await asyncio.gather(*(store.claim(1, 'pi') for store in stores))
        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        assert winners[0]['row_id'] == row['row_id']
        assert await stores[0].claim(1, 'pi') is None
        assert await stores[1].claim(1, 'pi') is None
    finally:
        await first.close()
        await second.close()


@pytest.mark.asyncio
async def test_cross_connection_reorders_read_fresh_positions(tmp_path):
    import asyncio
    path = str(tmp_path / 'reorder.db')
    first, second = Database(path), Database(path)
    await first.connect()
    await second.connect()
    try:
        stores = [FollowupStore(first), FollowupStore(second)]
        rows = [await stores[0].enqueue(thread_id=1, agent_id='pi', message_id=i, content=str(i)) for i in range(3)]
        # Two downward moves of the first row must move it to the end.
        assert await asyncio.gather(*(store.reorder(rows[0]['row_id'], 'down', thread_id=1, agent_id='pi') for store in stores)) == [True, True]
        listed = await stores[0].list(thread_id=1, agent_id='pi')
        assert [item['row_id'] for item in listed] == [rows[i]['row_id'] for i in (1, 2, 0)]
        assert len({item['ordinal'] for item in listed}) == 3
    finally:
        await first.close()
        await second.close()


@pytest.mark.asyncio
async def test_completion_requires_admitted_owner_and_never_replays(db):
    store = FollowupStore(db)
    original = await store.enqueue(thread_id=1, agent_id='pi', message_id=1, content='done')
    claim = await store.claim(1, 'pi')
    with pytest.raises(ValueError, match='no longer owned'):
        await store.complete(claim)
    await store.transition_claim(claim, admitted=True)
    with pytest.raises(ValueError, match='no longer owned'):
        await store.complete({**claim, 'claim_token': 'foreign'})
    await store.complete(claim)
    assert await store.list(thread_id=1, agent_id='pi') == []
    await store.recover()
    assert await store.claim(1, 'pi') is None
    new = await store.enqueue(thread_id=1, agent_id='pi', message_id=2, content='new')
    assert new['row_id'] < original['row_id']


@pytest.mark.asyncio
async def test_uncertain_review_discards_only_explicit_scoped_row(db):
    store = FollowupStore(db)
    old = await store.enqueue(thread_id=1, agent_id='pi', message_id=1, content='uncertain')
    pending = await store.enqueue(thread_id=1, agent_id='pi', message_id=2, content='pending')
    owner = await store.claim(1, 'pi')
    await store.recover()
    assert not await store.discard_uncertain(old['row_id'], thread_id=2, agent_id='pi')
    assert not await store.discard_uncertain(old['row_id'], thread_id=1, agent_id='acp')
    assert not await store.discard_uncertain(pending['row_id'], thread_id=1, agent_id='pi')
    with pytest.raises(ValueError, match='no longer owned'):
        await store.transition_claim(owner)
    assert await store.discard_uncertain(old['row_id'], thread_id=1, agent_id='pi')
    assert not await store.discard_uncertain(old['row_id'], thread_id=1, agent_id='pi')
    assert (await store.claim(1, 'pi'))['row_id'] == pending['row_id']


@pytest.mark.asyncio
async def test_v8_upgrade_preserves_messages_and_is_idempotent(tmp_path):
    import sqlite3
    from pathlib import Path
    import json
    path = str(tmp_path / 'upgrade.db')
    with sqlite3.connect(path) as connection:
        connection.executescript((Path(__file__).parent / 'fixtures/schema-v8.sql').read_text())
        cursor = connection.execute('INSERT INTO interactions(data) VALUES(?)',
                                    (json.dumps({'type': 'user', 'content': 'keep me', 'session_id': 'default'}),))
        message = cursor.lastrowid
        assert connection.execute('SELECT version FROM schema_version').fetchone()[0] == 8
    db = Database(path)
    try:
        await db.connect()
        assert (await db.get_interaction(message))['data']['content'] == 'keep me'
        item = await FollowupStore(db).enqueue(thread_id=message, agent_id='pi', message_id=message, content='next')
        await db.close()
        await db.connect()
        assert (await db.get_interaction(message))['data']['content'] == 'keep me'
        listing = await FollowupStore(db).list(thread_id=message, agent_id='pi')
        assert [row['row_id'] for row in listing] == [item['row_id']]
        async with db.transaction() as connection:
            async with connection.execute('SELECT version FROM schema_version') as cursor:
                assert (await cursor.fetchone())[0] == 9
    finally:
        await db.close()

@pytest.mark.asyncio
async def test_promoted_steer_appends_after_existing_steers_before_normal_queue(db):
    store = FollowupStore(db)
    normal = await store.enqueue(thread_id=1, agent_id='pi', message_id=1, content='normal')
    promoted = await store.enqueue(thread_id=1, agent_id='pi', message_id=2, content='promoted')
    first = await store.enqueue(thread_id=1, agent_id='pi', message_id=3, content='first steer', steer=True)
    second = await store.enqueue(thread_id=1, agent_id='pi', message_id=4, content='second steer', steer=True)
    owner = await store.claim_for_steer(promoted['row_id'], thread_id=1, agent_id='pi')
    await store.transition_claim(owner, defer_steer=True)
    claimed = [await store.claim(1, 'pi') for _ in range(4)]
    assert [row['row_id'] for row in claimed] == [first['row_id'], second['row_id'], promoted['row_id'], normal['row_id']]
