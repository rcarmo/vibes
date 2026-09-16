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
async def test_explicit_ids_context_missing_and_row_windows_stay_session_scoped(db):
    from vibes.sessions import SessionStore
    other = await SessionStore(db).create('Private')
    ids = [await db.create_interaction({'type': 'user', 'content': f'row {i}'}) for i in range(6)]
    private = await db.create_interaction({'type': 'user', 'content': 'private', 'session_id': other['id']})
    tools = MessageTools(db._connection, session_id='default')
    result = await tools.query('get', row_ids=[ids[2], private, 999999], context_before=2, context_after=2, limit=10)
    assert [m['row_id'] for m in result['messages']] == list(reversed(ids[:5]))
    assert result['missing_row_ids'] == [private, 999999]
    assert [m['row_id'] for m in (await tools.query('search', query='row', after_row=ids[1], limit=2))['messages']] == list(reversed(ids[4:6]))
    assert [m['row_id'] for m in (await tools.query('search', query='row', before_row=ids[4], limit=2))['messages']] == list(reversed(ids[2:4]))
    bounded = await tools.query('search', query='row', after_row=ids[1], before_row=ids[5], limit=2)
    assert [m['row_id'] for m in bounded['messages']] == list(reversed(ids[3:5]))
    assert bounded['has_more']
    assert bounded['next_before_row'] == ids[3]
    page_two = await tools.query('search', query='row', after_row=ids[1], before_row=bounded['next_before_row'], limit=2)
    assert [m['row_id'] for m in page_two['messages']] == [ids[2]]
    assert not page_two['has_more']
    assert private not in {m['row_id'] for m in bounded['messages'] + page_two['messages']}
    for kwargs in [
        {'before_row': ids[1], 'after_row': ids[4]}, {'before_row': ids[2], 'after_row': ids[2]}, {'after_row': True},
        {'context_before': 21}, {'context_after': -1},
    ]:
        with pytest.raises(ValueError):
            await tools.query('get', row_ids=[ids[2]], **kwargs)
    with pytest.raises(ValueError):
        await tools.query('search', query='row', context_before=1)


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


@pytest.mark.asyncio
async def test_attachment_text_and_scope(db):
    text_id = await db.create_media('text.txt', 'text/plain', b'hello ' * 6000)
    binary_id = await db.create_media('binary.bin', 'application/octet-stream', b'\x00\xff')
    secret_id = await db.create_media('text.txt', 'text/plain', b'secret')
    root = await db.create_interaction({'type': 'user', 'content': 'uploads', 'media_ids': [text_id, binary_id]})
    await db.create_interaction({'type': 'user', 'content': 'other', 'media_ids': [secret_id]})
    tools = MessageTools(db._connection, thread_id=root)
    preview = await tools.query('attachment', media_id=text_id)
    assert len(preview['text']) == 24000
    assert preview['truncated']
    binary = await tools.query('attachment', media_id=binary_id)
    assert 'text' not in binary
    assert binary['size'] == 2
    with pytest.raises(ValueError):
        await tools.query('attachment', media_id=secret_id)
    with pytest.raises(ValueError):
        await tools.query('attachment', media_id=True)


@pytest.mark.asyncio
async def test_session_scope_covers_messages_and_attachment_authorization(db):
    SessionStore = importlib.import_module('vibes.sessions').SessionStore
    other = await SessionStore(db).create('Other')
    secret = await db.create_media('private.txt', 'text/plain', b'secret')
    public = await db.create_interaction({'type': 'user', 'content': 'needle default'})
    hidden = await db.create_interaction({'type': 'user', 'content': 'needle private', 'session_id': other['id'], 'media_ids': [secret]})
    tools = MessageTools(db._connection, session_id='default')
    assert [m['row_id'] for m in (await tools.query('get', row_ids=[public, hidden]))['messages']] == [public]
    assert [m['row_id'] for m in (await tools.query('search', query='needle'))['messages']] == [public]
    with pytest.raises(ValueError):
        await tools.query('attachment', media_id=secret)
    scoped = MessageTools(db._connection, session_id=other['id'])
    assert (await scoped.query('attachment', media_id=secret))['text'] == 'secret'
    with pytest.raises(ValueError):
        MessageTools(db._connection, session_id='default', workspace_access=True)


@pytest.mark.asyncio
async def test_session_reference_resolution_respects_trusted_scope(db):
    from vibes.sessions import SessionStore
    other = await SessionStore(db).create('Private chat')
    root = await db.create_interaction({'type': 'user', 'content': 'text', 'session_id': other['id']})
    reference = '@session:' + other['id']
    scoped = MessageTools(db._connection, session_id='default')
    assert await scoped.query('resolve_session', reference=reference) == {'session': None}
    assert await scoped.query('resolve_session', reference='@session:missing') == {'session': None}
    for tools in (MessageTools(db._connection, workspace_access=True),
                  MessageTools(db._connection, session_id=other['id']),
                  MessageTools(db._connection, thread_id=root)):
        result = await tools.query('resolve_session', reference=reference)
        assert result == {'session': {'id': other['id'], 'name': 'Private chat', 'archived': False}}
    thread = MessageTools(db._connection, thread_id=root)
    assert await thread.query('resolve_session', reference='@session:default') == {'session': None}
    for reference in (None, 'default', '@session:', '@session:a b', '@session:' + 'x' * 513):
        with pytest.raises(ValueError):
            await scoped.query('resolve_session', reference=reference)
