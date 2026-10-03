"""Offline contracts; never use inherited credentials or call a model."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from vibes import copilot_client as mod


class Session:
    session_id = 'synthetic-sdk'
    def __init__(self):
        self.handler = None
        self.abort = AsyncMock()
    def on(self, handler):
        self.handler = handler
        return lambda: setattr(self, 'handler', None)
    async def send(self, content):
        for kind, data in [('assistant.message_delta', {'deltaContent': 'Hello '}),
                           ('assistant.message_delta', {'deltaContent': 'world'}),
                           ('assistant.message', {'content': 'Hello world'}), ('session.idle', {})]:
            self.handler(SimpleNamespace(type=kind, data=data))


@pytest.fixture
def setup(monkeypatch, tmp_path):
    session = Session()
    client = SimpleNamespace(start=AsyncMock(), stop=AsyncMock(), get_status=AsyncMock(return_value={'version': '1.0.85'}),
        create_session=AsyncMock(return_value=session), resume_session=AsyncMock(return_value=session),
        rpc=SimpleNamespace(sessions=SimpleNamespace(save=AsyncMock())))
    factory = Mock(return_value=client)
    ffi = Mock(return_value='native-only')
    sdk = SimpleNamespace(CopilotClient=factory, RuntimeConnection=SimpleNamespace(for_inprocess=ffi),
        RemoteSessionMode=SimpleNamespace(OFF='off'), Tool=lambda **kw: SimpleNamespace(**kw))
    config = SimpleNamespace(copilot_state_dir=str(tmp_path/'state'), copilot_use_logged_in_user=False,
        copilot_start_timeout=2, copilot_event_timeout=2, permission_timeout=.1,
        copilot_model=None, copilot_available_tools=[], copilot_skill_directories=[])
    monkeypatch.setattr(mod, '_sdk', lambda: sdk)
    monkeypatch.setattr(mod, 'get_config', lambda: config)
    return mod.CopilotBackend(), client, session, factory, ffi


def test_draft_preview_is_bounded_self_contained_snapshot():
    text = '\n'.join(f'line-{i}' for i in range(25))
    result = mod._draft_preview(text)
    assert result['text'] == '\n'.join(text.split('\n')[-9:])
    assert result['total_lines'] == 25
    assert len(mod._draft_preview('x' * 20000)['text']) == 16000
    # Missing a lossy preview must not lose earlier words from the next snapshot.
    assert mod._draft_preview('one two three')['text'] == 'one two three'


@pytest.mark.asyncio
async def test_only_ffi_and_no_implicit_auth(setup):
    backend, client, session, factory, ffi = setup
    await backend.start()
    ffi.assert_called_once_with()
    opts = factory.call_args.kwargs
    assert opts['connection'] == 'native-only'
    assert opts['use_logged_in_user'] is False
    assert opts['enable_remote_sessions'] is False
    assert opts['mode'] == 'empty'
    assert 'env' not in opts and 'working_directory' not in opts
    assert backend.status()['ready']
    await backend.stop()
    client.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_native_failure_has_no_fallback(setup):
    backend, client, *_ = setup
    client.start.side_effect = RuntimeError('synthetic native failure')
    with pytest.raises(RuntimeError, match='unavailable'):
        await backend.start()
    assert not backend.status()['ready']
    client.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_and_binding(setup, monkeypatch):
    backend, client, session, *_ = setup
    from vibes import agent_attachments
    monkeypatch.setattr(agent_attachments, 'active', {'mode':'copilot-ffi','session_id':'chat','turn_id':'turn'})
    store = SimpleNamespace(backend_binding=AsyncMock(return_value=None), bind_backend=AsyncMock())
    seen = []
    async def callback(data):
        seen.append(data)
    result = await backend.send('hello', 1, callback, chat_id='chat', store=store)
    assert result['text'] == 'Hello world'
    chunks = [x for x in seen if x['type'] == 'message_chunk']
    assert ''.join(x['delta'] for x in chunks) == 'Hello world'
    assert [x['text'] for x in chunks] == ['Hello ', 'Hello world']
    assert all(x['mode'] == 'replace' for x in chunks)
    assert [x['delta_reset'] for x in chunks] == [True, False]
    assert seen[0] == {'type': 'writing', 'title': 'Writing response'}
    opts = client.create_session.call_args.kwargs
    assert opts['remote_session'] == 'off'
    assert opts['available_tools'] == ['custom:vibes_attach_file','custom:plan','custom:open_file','custom:messages']
    store.bind_backend.assert_awaited_once()
    assert backend.active is None and session.handler is None


@pytest.mark.asyncio
async def test_resume_not_replayed(setup):
    backend, client, *_ = setup
    await backend.start()
    store = SimpleNamespace(backend_binding=AsyncMock(return_value={'conversation_id':'saved'}))
    await backend._session('chat',store)
    assert client.resume_session.call_args.args == ('saved',)
    assert client.resume_session.call_args.kwargs['continue_pending_work'] is False
    client.create_session.assert_not_called()


@pytest.mark.asyncio
async def test_approval_bound_to_turn_and_single_use(setup):
    backend, _, session, *_ = setup
    owner={'chat_id':'chat','turn_id':'turn','thread_id':1,'session':session,'cancelled':False}
    backend.active=owner
    payloads=[]
    async def publish(payload):
        payloads.append(payload)
    backend.request_callback=publish
    task=asyncio.create_task(backend._decision('Synthetic',{'command':'example'},[{'optionId':'allow'},{'optionId':'deny'}]))
    await asyncio.sleep(0)
    rid=payloads[0]['request_id']
    assert not backend.respond(rid,'anything')
    assert backend.respond(rid,'allow')
    assert not backend.respond(rid,'allow')
    assert await task == 'allow'
    assert not backend.pending_requests()
    assert not backend.respond(rid,'allow')


@pytest.mark.asyncio
async def test_approval_timeout_denies(setup):
    backend, _, session, *_=setup
    backend.active={'chat_id':'chat','turn_id':'turn','thread_id':1,'session':session,'cancelled':False}
    backend.request_callback=AsyncMock()
    assert await backend._decision('x',{},[{'optionId':'allow'}]) == 'deny'
    assert not backend.pending


@pytest.mark.asyncio
async def test_stale_abort_rejected(setup):
    backend,_,session,*_=setup
    owner={'chat_id':'chat','session':session,'cancelled':False}
    backend.active=owner
    assert not await backend.abort('other',owner)
    assert not await backend.abort('chat',{})
    assert await backend.abort('chat',owner)
    session.abort.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrong_runtime_is_rejected(setup):
    backend, client, *_ = setup
    client.get_status.return_value = {'version': 'unexpected'}
    with pytest.raises(RuntimeError):
        await backend.start()
    assert not backend.status()['ready']
    client.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_during_start_cleans_native_host(setup):
    backend, client, *_ = setup
    entered = asyncio.Event()
    async def wait_start():
        entered.set()
        await asyncio.Event().wait()
    client.start.side_effect = wait_start
    task = asyncio.create_task(backend.start())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    client.stop.assert_awaited_once()
    assert not backend.status()['ready']


@pytest.mark.asyncio
async def test_failed_abort_does_not_skip_host_cleanup(setup):
    backend, client, session, *_ = setup
    await backend.start()
    session.abort.side_effect = RuntimeError('synthetic abort failure')
    backend.active = {'chat_id':'chat', 'session':session, 'cancelled':False}
    await backend.stop()
    client.stop.assert_awaited_once()
    assert backend.poisoned


@pytest.mark.asyncio
async def test_timeout_prevents_next_turn(setup, monkeypatch):
    backend, client, session, *_ = setup
    from vibes import agent_attachments
    monkeypatch.setattr(agent_attachments,'active',{'mode':'copilot-ffi','session_id':'chat','turn_id':'turn'})
    monkeypatch.setattr(mod.get_config(),'copilot_event_timeout',.02)
    session.send = AsyncMock()
    store=SimpleNamespace(backend_binding=AsyncMock(return_value=None),bind_backend=AsyncMock())
    with pytest.raises(asyncio.TimeoutError):
        await backend.send('hi',1,AsyncMock(),chat_id='chat',store=store)
    assert backend.poisoned and backend.active is None
    with pytest.raises(RuntimeError,match='restart'):
        await backend.start()


@pytest.mark.asyncio
async def test_cross_session_tool_rejected(setup):
    backend, _, session, *_ = setup
    backend.active={'chat_id':'chat','session':session,'cancelled':False}
    with pytest.raises(PermissionError):
        backend._owner('other',session.session_id)
    with pytest.raises(PermissionError):
        backend._owner('chat','other-sdk-session')


@pytest.mark.asyncio
async def test_admission_timeout_preserves_identity_and_refuses_replacement(setup, monkeypatch):
    backend, client, session, *_ = setup
    from vibes import agent_attachments
    monkeypatch.setattr(agent_attachments, 'active', {'mode':'copilot-ffi','session_id':'chat','turn_id':'turn'})
    monkeypatch.setattr(mod.get_config(), 'copilot_start_timeout', .02)
    entered = asyncio.Event()
    async def send(*args):
        entered.set()
        await asyncio.Event().wait()
    session.send = send
    store = SimpleNamespace(backend_binding=AsyncMock(return_value=None),bind_backend=AsyncMock())
    with pytest.raises(asyncio.TimeoutError):
        await backend.send('test',1,AsyncMock(),chat_id='chat',store=store)
    assert entered.is_set() and backend.poisoned
    store.bind_backend.assert_awaited_once()
    assert backend.active is None


@pytest.mark.asyncio
async def test_shutdown_waits_for_active_idle_before_native_stop(setup, monkeypatch):
    backend, client, session, *_ = setup
    from vibes import agent_attachments
    monkeypatch.setattr(agent_attachments, 'active', {'mode':'copilot-ffi','session_id':'chat','turn_id':'turn'})
    entered = asyncio.Event()
    async def send(*args):
        entered.set()
    async def abort():
        session.handler(SimpleNamespace(type='session.idle',data={}))
    session.send = send
    session.abort.side_effect = abort
    store = SimpleNamespace(backend_binding=AsyncMock(return_value=None),bind_backend=AsyncMock())
    task = asyncio.create_task(backend.send('test',1,AsyncMock(),chat_id='chat',store=store))
    await entered.wait()
    await backend.stop()
    result = await task
    assert result['cancelled'] and not backend.poisoned
    client.stop.assert_awaited_once()
    assert backend.active is None


@pytest.mark.asyncio
async def test_tool_completion_keeps_name_and_does_not_claim_success(setup, monkeypatch):
    backend, client, session, *_ = setup
    from vibes import agent_attachments
    monkeypatch.setattr(agent_attachments, 'active', {'mode':'copilot-ffi','session_id':'chat','turn_id':'turn'})
    async def send(*args):
        for kind, data in [('tool.execution_start', {'toolCallId':'x','toolName':'fixture'}),
                           ('tool.execution_partial_result', {'toolCallId':'x','partialOutput':'<' + 'a' * 17000}),
                           ('tool.execution_progress', {'toolCallId':'x','progressMessage':'working'}),
                           ('assistant.usage', {'inputTokens':123, 'outputTokens':45, 'cacheReadTokens':True, 'private':'secret'}),
                           ('tool.execution_complete', {'toolCallId':'x','success':False,'result':{'content':'final text','structuredContent':{'private':'secret'}}}), ('session.idle', {})]:
            session.handler(SimpleNamespace(type=kind, data=data))
    session.send = send
    store = SimpleNamespace(backend_binding=AsyncMock(return_value=None),bind_backend=AsyncMock())
    callback = AsyncMock()
    await backend.send('test',1,callback,chat_id='chat',store=store)
    assert callback.await_args_list[-1].args[0] == {'type':'tool_status','tool_call_id':'x','title':'fixture','status':'failed'}
    usage = next(call.args[0] for call in callback.await_args_list if call.args[0].get('type') == 'usage')
    assert usage['usage'] == {'input_tokens':123, 'output_tokens':45}
    assert usage['context_occupancy'] is None
    assert 'private' not in usage
    output = next(call.args[0] for call in callback.await_args_list if call.args[0].get('type') == 'tool_output')
    assert output['tool_call_id'] == 'x'
    assert len(output['content']) == 16000 and output['content_truncated'] is True
    assert any(call.args[0].get('progress') is True for call in callback.await_args_list)
    final_output = next(call.args[0] for call in callback.await_args_list if call.args[0].get("replace_output"))
    assert final_output["content"] == "final text"
    assert "secret" not in repr(final_output)


@pytest.mark.asyncio
async def test_disconnect_never_restarts_ffi(monkeypatch):
    from vibes.routes import sse
    monkeypatch.setattr(sse,'get_config',lambda:SimpleNamespace(default_agent='copilot-ffi',disconnect_timeout=1))
    monkeypatch.setattr(sse,'_clients',set())
    monkeypatch.setattr(sse,'_restart_task',None)
    sse._schedule_restart_if_needed()
    assert sse._restart_task is None

@pytest.mark.asyncio
async def test_messages_tool_rejects_scope_overrides_and_mutations(setup, monkeypatch):
    backend, client, session, factory, ffi = setup
    backend.sdk = SimpleNamespace(Tool=lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(backend, '_owner', lambda chat, session: True)
    tool = next(tool for tool in backend._tools('chat-a') if tool.name == 'messages')
    for args in [{'action': 'delete', 'row_ids': [1]}, {'action': 'get', 'row_ids': [1], 'session_id': 'chat-b'}]:
        with pytest.raises(ValueError):
            await tool.handler(SimpleNamespace(arguments=args, session_id='sdk'))

@pytest.mark.asyncio
async def test_ffi_messages_returns_only_current_chat_provenance(setup, monkeypatch, db):
    import importlib
    db_module = importlib.import_module('vibes.db')
    backend, *_ = setup
    owner = object()
    monkeypatch.setattr(backend, '_owner', lambda chat, session: owner)
    backend.sdk = SimpleNamespace(Tool=lambda **kw: SimpleNamespace(**kw), ToolResult=lambda **kw: SimpleNamespace(**kw))
    from vibes.sessions import SessionStore
    a = await SessionStore(db).create('chat-a')
    b = await SessionStore(db).create('chat-b')
    first = await db.create_interaction({'sender':'me', 'type':'user', 'content':'visible request', 'session_id':a['id']})
    private = await db.create_interaction({'sender':'bot', 'type':'agent', 'content':'private other chat', 'session_id':b['id']})
    async def get_db():
        return db
    monkeypatch.setattr(db_module, 'get_db', get_db)
    tool = next(tool for tool in backend._tools(a['id']) if tool.name == 'messages')
    result = await tool.handler(SimpleNamespace(arguments={'action': 'get', 'row_ids': [first, private]}, session_id='sdk'))
    assert f'[{first}] me: visible request' in result.text_result_for_llm
    assert f'[{private}]' not in result.text_result_for_llm
    assert 'private other chat' not in result.text_result_for_llm

@pytest.mark.asyncio
async def test_native_command_discovery_is_not_an_execution_claim(setup, monkeypatch):
    backend, *_ = setup
    commands = SimpleNamespace(commands=[SimpleNamespace(to_dict=lambda: {'name': 'native', 'kind': 'builtin', 'privateToken': 'secret', 'description': 'bad\nlabel'})])
    skills = SimpleNamespace(skills=[SimpleNamespace(to_dict=lambda: {'name': 'loaded', 'enabled': True})])
    session = SimpleNamespace(rpc=SimpleNamespace(commands=SimpleNamespace(list=AsyncMock(return_value=commands)), skills=SimpleNamespace(list=AsyncMock(return_value=skills))))
    monkeypatch.setattr(backend, '_session', AsyncMock(return_value=session))
    result = await backend.command_catalogue('chat', object())
    assert result['available'] is True
    assert result['commands'][0] == {'name': 'native', 'kind': 'builtin'}
    assert 'secret' not in repr(result)
    assert result['truncated'] is False
    assert result['skills'][0]['name'] == 'loaded'
    session.rpc.commands.list.side_effect = RuntimeError('provider private details')
    assert await backend.command_catalogue('chat', object()) == {'available': False, 'commands': [], 'skills': []}

@pytest.mark.asyncio
async def test_compaction_uses_native_history_without_reset(setup, monkeypatch):
    backend, *_ = setup
    session = SimpleNamespace(rpc=SimpleNamespace(history=SimpleNamespace(compact=AsyncMock(return_value=SimpleNamespace(success=True, messages_removed=2, tokens_removed=0, context_window=None)))))
    monkeypatch.setattr(backend, '_session', AsyncMock(return_value=session))
    result = await backend.compact('chat', object())
    assert result == {'success': True, 'messages_removed': 2, 'tokens_removed': 0, 'context_window': None}
    session.rpc.history.compact.assert_awaited_once_with(timeout=120)
    async with backend.turn_lock:
        with pytest.raises(RuntimeError, match='active turn'):
            await backend.compact('chat', object())

@pytest.mark.asyncio
async def test_compaction_cancellation_is_native_and_chat_scoped(setup):
    backend, *_ = setup
    history = SimpleNamespace(abort_manual_compaction=AsyncMock(return_value=SimpleNamespace(to_dict=lambda: {'aborted': True})))
    backend.sessions['chat-a'] = SimpleNamespace(rpc=SimpleNamespace(history=history))
    backend.compacting_sessions.add('chat-a')
    assert await backend.cancel_compaction('chat-b') is False
    assert await backend.cancel_compaction('chat-a') == {'aborted': True}
    history.abort_manual_compaction.assert_awaited_once_with(timeout=10)

@pytest.mark.asyncio
async def test_lane_shutdown_cancels_compaction_without_stopping_shared_client():
    from vibes.copilot_host import ConversationLane
    host = SimpleNamespace(client=SimpleNamespace(stop=AsyncMock()), runtime=SimpleNamespace(sdk=None))
    lane = ConversationLane(host, 'chat')
    lane.compacting_sessions.add('chat')
    lane.cancel_compaction = AsyncMock(return_value={'aborted': True})
    await lane.stop()
    lane.cancel_compaction.assert_awaited_once_with('chat')
    host.client.stop.assert_not_awaited()

@pytest.mark.asyncio
async def test_failed_native_compaction_clears_state_and_releases_lane(setup, monkeypatch):
    backend, *_ = setup
    history = SimpleNamespace(compact=AsyncMock(side_effect=RuntimeError('native failure')))
    session = SimpleNamespace(rpc=SimpleNamespace(history=history))
    monkeypatch.setattr(backend, '_session', AsyncMock(return_value=session))
    with pytest.raises(RuntimeError, match='native failure'):
        await backend.compact('chat', object())
    assert not backend.compacting_sessions
    assert not backend.turn_lock.locked()
    assert await backend.cancel_compaction('chat') is False

@pytest.mark.asyncio
async def test_cancelled_compaction_task_releases_lane(setup, monkeypatch):
    import asyncio
    backend, *_ = setup
    entered = asyncio.Event()
    async def compact(**kwargs):
        entered.set()
        await asyncio.Event().wait()
    session = SimpleNamespace(rpc=SimpleNamespace(history=SimpleNamespace(compact=compact)))
    monkeypatch.setattr(backend, '_session', AsyncMock(return_value=session))
    task = asyncio.create_task(backend.compact('chat', object()))
    await entered.wait()
    assert backend.compacting_sessions == {'chat'}
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not backend.compacting_sessions
    assert not backend.turn_lock.locked()

@pytest.mark.asyncio
async def test_busy_command_discovery_never_calls_native_session(setup, monkeypatch):
    backend, *_ = setup
    session = AsyncMock()
    monkeypatch.setattr(backend, '_session', session)
    async with backend.turn_lock:
        result = await backend.command_catalogue('chat', object())
    assert result == {'available': False, 'busy': True, 'commands': [], 'skills': []}
    session.assert_not_awaited()

@pytest.mark.asyncio
async def test_messages_session_reference_cannot_expand_ffi_scope(setup, monkeypatch, tmp_path):
    from vibes.db import Database
    from vibes import db as db_module
    backend, *_ = setup
    backend.sdk = SimpleNamespace(Tool=lambda **kw: SimpleNamespace(**kw), ToolResult=lambda **kw: SimpleNamespace(**kw))
    monkeypatch.setattr(backend, '_owner', lambda chat, session: True)
    db = Database(tmp_path / 'references.db')
    await db.connect()
    try:
        from vibes.sessions import SessionStore
        own = await SessionStore(db).create('Own')
        other = await SessionStore(db).create('Private')
        async def get_db():
            return db
        monkeypatch.setattr(db_module, 'get_db', get_db)
        tool = next(tool for tool in backend._tools(own['id']) if tool.name == 'messages')
        assert 'resolve_session' in tool.parameters['properties']['action']['enum']
        for target, expected in [(own['id'], 'Own'), (other['id'], None)]:
            result = await tool.handler(SimpleNamespace(arguments={'action': 'resolve_session', 'reference': f'@session:{target}'}, session_id='sdk'))
            payload = __import__('json').loads(result.text_result_for_llm)
            assert (payload['session']['name'] if payload['session'] else None) == expected
    finally:
        await db.close()

@pytest.mark.asyncio
async def test_native_catalogue_caps_both_sources_and_drops_invalid_names(setup, monkeypatch):
    backend, *_ = setup
    entries = [SimpleNamespace(to_dict=lambda: {'name': 'valid', 'description': 'x' * 513}) for _ in range(130)]
    entries[0] = SimpleNamespace(to_dict=lambda: {'name': 'bad\nname'})
    session = SimpleNamespace(rpc=SimpleNamespace(
        commands=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(commands=entries))),
        skills=SimpleNamespace(list=AsyncMock(return_value=SimpleNamespace(skills=entries)))))
    monkeypatch.setattr(backend, '_session', AsyncMock(return_value=session))
    result = await backend.command_catalogue('chat', object())
    assert result['truncated'] is True
    assert len(result['commands']) == len(result['skills']) == 127
    assert all(row == {'name': 'valid'} for row in result['commands'] + result['skills'])

@pytest.mark.asyncio
async def test_native_catalogue_session_failure_is_unavailable_and_releases_lane(setup, monkeypatch):
    backend, *_ = setup
    monkeypatch.setattr(backend, '_session', AsyncMock(side_effect=RuntimeError('private startup diagnostic')))
    result = await backend.command_catalogue('chat', object())
    assert result == {'available': False, 'commands': [], 'skills': []}
    assert not backend.turn_lock.locked()
    assert 'private' not in repr(result)
