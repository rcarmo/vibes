import importlib
import pytest

MessageTools = importlib.import_module('vibes.message_tools').MessageTools


@pytest.mark.asyncio
async def test_thread_scope_applies_to_get_and_search(db):
    root = await db.create_interaction({'type': 'user', 'content': 'needle root'})
    reply = await db.create_interaction({'type': 'agent', 'content': 'needle reply', 'thread_id': root})
    other = await db.create_interaction({'type': 'user', 'content': 'needle private'})
    tools = MessageTools(db._connection, thread_id=root)
    for result in [await tools.query('get', row_ids=[root, reply, other]), await tools.query('search', query='needle')]:
        assert {m['row_id'] for m in result['messages']} == {root, reply}
        assert not result['has_more']


@pytest.mark.asyncio
async def test_explicit_scope_bounds_and_pagination(db):
    with pytest.raises(ValueError):
        MessageTools(db._connection)
    tools = MessageTools(db._connection, workspace_access=True)
    ids = [await db.create_interaction({'type': 'user', 'content': 'needle ' + 'x' * 10000, 'secret_metadata': 'not exposed'}) for _ in range(8)]
    first = await tools.query('search', query='needle', limit=2)
    assert first['has_more']
    assert all(len(m['content']) <= 4000 and m['content_truncated'] for m in first['messages'])
    assert 'secret_metadata' not in str(first)
    second = await tools.query('search', query='needle', before_row=first['next_before_row'], limit=2)
    assert not {m['row_id'] for m in first['messages']} & {m['row_id'] for m in second['messages']}
    result = await tools.query('get', row_ids=ids, limit=50)
    assert sum(len(m['content']) for m in result['messages']) <= 24000
    for args in [{'action': 'delete'}, {'action': 'search', 'query': ''}, {'action': 'get', 'row_ids': [True]}, {'action': 'search', 'query': 'needle', 'limit': 51}]:
        with pytest.raises(ValueError):
            await tools.query(**args)


@pytest.mark.asyncio
async def test_attachment_references_are_scoped_bounded_and_sanitized(db):
    root = await db.create_interaction({'type': 'user', 'content': 'files', 'media_ids': [1, 1, True, -2, '3'] + list(range(2, 100))})
    hidden = await db.create_interaction({'type': 'user', 'content': 'private', 'media_ids': [999]})
    tools = MessageTools(db._connection, thread_id=root)
    result = await tools.query('get', row_ids=[root, hidden])
    assert len(result['messages']) == 1
    message = result['messages'][0]
    assert message['media_ids'] == list(range(1, 51))
    assert message['attachment_references'][0] == 'attachment:1'
    assert 'attachment:999' not in str(result)
    malformed = await db.create_interaction({'type': 'user', 'content': 'bad metadata', 'media_ids': 'not a list'})
    result = await MessageTools(db._connection, workspace_access=True).query('get', row_ids=[malformed])
    assert result['messages'][0]['attachment_references'] == []
