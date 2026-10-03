import asyncio
import aiosqlite
import pytest
from vibes.durable_queue import DurableQueue


@pytest.mark.asyncio
async def test_restart_never_replays_claimed_or_admitted_work(tmp_path):
    path = tmp_path / 'queue.db'
    async with aiosqlite.connect(path) as connection:
        queue = DurableQueue(connection)
        await queue.initialise()
        first = await queue.enqueue('a', {'text': 'first'})
        second = await queue.enqueue('a', {'text': 'second'})
        await queue.enqueue('b', {'text': 'private'})
        assert (await queue.claim('a'))['id'] == first
    async with aiosqlite.connect(path) as connection:
        queue = DurableQueue(connection)
        await queue.initialise()
        await queue.recover_after_restart()
        rows = await queue.list('a')
        assert rows[0]['state'] == 'uncertain'
        assert (await queue.claim('a'))['id'] == second
        with pytest.raises(ValueError):
            await queue.admitted(second, 'b')
        await queue.admitted(second, 'a')
    async with aiosqlite.connect(path) as connection:
        queue = DurableQueue(connection)
        await queue.initialise()
        assert await queue.claim('a') is None
        assert [row['state'] for row in await queue.list('a')] == ['uncertain', 'admitted']

@pytest.mark.asyncio
async def test_concurrent_claims_do_not_duplicate_delivery(tmp_path):
    import asyncio
    async with aiosqlite.connect(tmp_path / 'claims.db') as connection:
        queue = DurableQueue(connection)
        await queue.initialise()
        item = await queue.enqueue('chat', {'text': 'once'})
        results = await asyncio.gather(queue.claim('chat'), queue.claim('chat'))
        assert sum(result is not None for result in results) == 1
        assert next(result for result in results if result)['id'] == item

@pytest.mark.asyncio
async def test_initialisation_does_not_reclassify_live_claim(tmp_path):
    async with aiosqlite.connect(tmp_path / 'live.db') as connection:
        first = DurableQueue(connection)
        await first.initialise()
        item = await first.enqueue('chat', {'text': 'live'})
        await first.claim('chat')
        second = DurableQueue(connection)
        await second.initialise()
        assert (await second.list('chat'))[0]['state'] == 'claimed'
        await first.admitted(item, 'chat')
        assert (await second.list('chat'))[0]['state'] == 'admitted'


@pytest.mark.asyncio
async def test_independent_connections_cannot_claim_same_pending_item(tmp_path):
    path = tmp_path / 'dispatchers.db'
    async with aiosqlite.connect(path) as first, aiosqlite.connect(path) as second:
        a, b = DurableQueue(first), DurableQueue(second)
        await a.initialise()
        await b.initialise()
        item = await a.enqueue('chat', {'text': 'once'})
        claims = await asyncio.gather(a.claim('chat'), b.claim('chat'))
        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        assert winners[0]['id'] == item
        assert (await b.list('chat'))[0]['state'] == 'claimed'
        # A connection opening during dispatch must not perform crash recovery.
        await b.initialise()
        await a.admitted(item, 'chat')
        assert await b.claim('chat') is None
        assert (await b.list('chat'))[0]['state'] == 'admitted'
