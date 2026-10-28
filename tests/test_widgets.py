"""Widget artifacts are durable conversation data, never same-origin executable HTML."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes import agent_attachments
from vibes.routes import widgets
from vibes.sessions import SessionStore


@pytest.mark.asyncio
async def test_widget_publication_idempotence_scoping_and_durable_lookup(db, monkeypatch):
    monkeypatch.setattr(widgets, 'get_db', AsyncMock(return_value=db))
    events = AsyncMock()
    monkeypatch.setattr(widgets, 'broadcast_event', events)
    other = await SessionStore(db).create('Other widget chat')
    root = await db.create_interaction({'type': 'user', 'content': 'widget', 'session_id': 'default'})
    context = {'mode': 'pi', 'session_id': 'default', 'agent_id': 'pi', 'thread_id': root,
               'turn_id': 'widget-turn', 'cancelled': False}
    agent_attachments.set_active(context)
    params = {'html': '<script>window.synthetic=true</script><p>Widget</p>', 'title': 'Fixture',
              'interactive': True, 'request_id': 'widget-once'}
    try:
        first, retry = await asyncio.gather(*(
            widgets.publish_widget('pi', 'default', params, expected=context) for _ in range(2)))
        assert first == retry
        row = await db.get_interaction(first['message_id'])
        assert row['data']['session_id'] == 'default'
        assert row['data']['intermediate'] is True
        block = row['data']['content_blocks'][0]
        assert block['type'] == 'generated_widget'
        assert block['origin_chat_jid'] == 'gi:default'
        assert block['artifact']['html'] == params['html']
        assert [call.args[0] for call in events.await_args_list].count('new_post') == 1
        with pytest.raises(ValueError):
            await widgets.publish_widget('pi', 'default', {**params, 'html': 'changed'}, expected=context)
        with pytest.raises(PermissionError):
            await widgets.publish_widget('pi', other['id'], params, expected=context)
        app = web.Application()
        widgets.setup_routes(app)
        async with TestClient(TestServer(app)) as client:
            response = await client.get(first['url'])
            assert response.status == 200 and response.content_type == 'application/json'
            assert response.headers['Cache-Control'] == 'no-store'
            assert response.headers['X-Content-Type-Options'] == 'nosniff'
            assert await response.json() == block
            async with db._connection.execute(
                "EXPLAIN QUERY PLAN SELECT data FROM interactions "
                "WHERE COALESCE(json_extract(data, '$.session_id'), 'default') = ? "
                "AND type = 'agent_response' "
                "AND json_extract(data, '$.content_blocks[0].type') = 'generated_widget' "
                "AND json_extract(data, '$.content_blocks[0].widget_id') = ?",
                ('default', first['widget_id']),
            ) as cursor:
                query_plan = [row['detail'] for row in await cursor.fetchall()]
            assert any('idx_interactions_widget_lookup' in detail for detail in query_plan)
            assert (await client.get(f"/api/sessions/{other['id']}/widgets/{first['widget_id']}")).status == 404
            assert (await client.get('/api/sessions/default/widgets/not-a-valid-id')).status == 404
            await db.close()
            await db.connect()
            assert (await client.get(first['url'])).status == 200
            await db.delete_interactions([first['message_id']])
            assert (await client.get(first['url'])).status == 404
    finally:
        agent_attachments.clear_active(context)


@pytest.mark.asyncio
async def test_widget_route_token_origin_validation_and_cancelled_admission(db, monkeypatch):
    monkeypatch.setattr(widgets, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setattr(widgets, 'broadcast_event', AsyncMock())
    root = await db.create_interaction({'type': 'user', 'content': 'widget'})
    context = {'mode': 'acp', 'session_id': 'default', 'agent_id': 'acp', 'thread_id': root,
               'turn_id': 'cancelled-widget', 'cancelled': False}
    agent_attachments.set_active(context)
    def resolve(token):
        if token != 'valid':
            raise PermissionError('Invalid token')
        return 'acp', 'default'
    monkeypatch.setattr(agent_attachments, 'resolve_token', resolve)
    app = web.Application()
    widgets.setup_routes(app)
    try:
        async with TestClient(TestServer(app)) as client:
            path = '/internal/agent-tools/dashboard-widget'
            params = {'html': '<p>Fixture</p>', 'request_id': 'one'}
            headers = {'Authorization': 'Bearer valid'}
            assert (await client.post(path, json=params)).status == 403
            assert (await client.post(path, json=params, headers={**headers, 'Origin': 'http://localhost'})).status == 403
            for invalid in [[], {}, {**params, 'session_id': 'foreign'}, {**params, 'html': 'x' * (widgets.MAX_HTML_BYTES + 1)},
                            {**params, 'interactive': 1}, {**params, 'title': []}]:
                assert (await client.post(path, json=invalid, headers=headers)).status == 400
            response = await client.post(path, json=params, headers=headers)
            assert response.status == 201
            from vibes.messages_mcp import MessagesMCP
            server = MessagesMCP(None, attachment_url=str(client.make_url('/internal/agent-tools/attach-file')),
                                 attachment_token='valid', attachment_session='default')
            result = await server.send_dashboard_widget('<p>MCP widget</p>', request_id='mcp-widget')
            assert result['session_id'] == 'default'
            assert (await client.get(result['url'])).status == 200
            # Cancellation while admission waits on the database lock cannot publish.
            async with db.transaction():
                pending = asyncio.create_task(widgets.publish_widget('acp', 'default', {
                    **params, 'request_id': 'cancel-before-store',
                }, expected=context))
                await asyncio.sleep(.02)
                context['cancelled'] = True
            with pytest.raises(PermissionError):
                await pending
            async with db._connection.execute("SELECT COUNT(*) AS n FROM interactions WHERE type='agent_response'") as cursor:
                assert (await cursor.fetchone())['n'] == 2
            assert (await client.post(path, json={**params, 'request_id': 'late'}, headers=headers)).status == 403
    finally:
        agent_attachments.clear_active(context)
