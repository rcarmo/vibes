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
