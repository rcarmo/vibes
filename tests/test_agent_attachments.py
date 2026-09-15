import asyncio
import io
import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web
from PIL import Image

from vibes import agent_attachments as attachments
from vibes.message_tools import MessageTools
from vibes.messages_mcp import MessagesMCP
from vibes.routes import pi_tools
from vibes.sessions import SessionStore


def png():
    out = io.BytesIO()
    Image.new('RGB', (16, 12), '#336699').save(out, format='PNG')
    return out.getvalue()


def test_attachment_file_boundaries(tmp_path):
    image = tmp_path / 'chart.png'
    image.write_bytes(png())
    name, mime, data, thumbnail, meta = attachments.read_attachment_file(tmp_path, str(image))
    assert name == 'chart.png' and mime == 'image/png' and data == png()
    assert thumbnail and meta['width'] == 16 and meta['height'] == 12
    assert attachments.read_attachment_file(tmp_path, 'chart.png', kind='file')[1] == 'application/octet-stream'
    (tmp_path / 'link').symlink_to(image)
    os.mkfifo(tmp_path / 'fifo')
    for path in ['../chart.png', '/etc/passwd', 'link', 'fifo']:
        with pytest.raises((ValueError, OSError)):
            attachments.read_attachment_file(tmp_path, path)
    with pytest.raises(ValueError):
        attachments.read_attachment_file(tmp_path, 'chart.png', max_bytes=1)
    (tmp_path / 'bad.png').write_text('not an image')
    with pytest.raises(ValueError):
        attachments.read_attachment_file(tmp_path, 'bad.png')
    (tmp_path / 'drawing.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    assert attachments.read_attachment_file(tmp_path, 'drawing.svg')[4]['kind'] == 'file'
    with pytest.raises(ValueError):
        attachments.read_attachment_file(tmp_path, 'drawing.svg', kind='image')


@pytest.mark.asyncio
async def test_publish_immediate_scoped_idempotent_durable_and_inline(db, tmp_path):
    session = await SessionStore(db).create('Images')
    root = await db.create_interaction({'type': 'user_message', 'content': 'make an image', 'session_id': session['id']})
    context = {'mode': 'pi', 'session_id': session['id'], 'thread_id': root, 'turn_id': 'image-turn', 'agent_id': 'default', 'receipts': {}}
    (tmp_path / 'chart.png').write_bytes(png())
    params = {'path': 'chart.png', 'request_id': 'call-one'}
    with patch.object(attachments, 'active', context), patch.object(attachments, 'get_db', AsyncMock(return_value=db)), \
         patch.object(attachments.Path, 'cwd', return_value=tmp_path), patch('vibes.routes.sse.broadcast_event', AsyncMock()) as emit:
        results = await asyncio.gather(*(attachments.publish_file(params, 'pi') for _ in range(3)))
        assert results[0] == results[1] == results[2]
        result = results[0]
        row = await db.get_interaction(result['message_id'])
        assert row['data']['session_id'] == session['id']
        assert row['data']['intermediate'] is True
        assert row['data']['content_blocks'][0]['media_id'] == result['media_id']
        assert row['data']['media_ids'] == [result['media_id']]
        assert emit.call_args_list[0].args[0] == 'new_post'
        assert all(call.args[0] != 'agent_response' for call in emit.call_args_list)
        assert (await db.get_media_data(result['media_id']))[1] == png()
        assert len(await attachments.referenced_media(f'![chart]({result["reference"]})', session['id'])) == 1
        assert await attachments.referenced_media(result['reference'], 'default') == []
        with pytest.raises(ValueError):
            await attachments.publish_file({**params, 'name': 'different.png'}, 'pi')
        with pytest.raises(PermissionError):
            await attachments.publish_file(params, 'acp', session['id'])
        scoped = MessageTools(db._connection, session_id=session['id'])
        assert (await scoped.attachment(result['media_id']))['filename'] == 'chart.png'
    # The timeline row and blob remain after the runtime context is gone.
    assert (await db.get_interaction(result['message_id']))['data']['media_ids']


@pytest.mark.asyncio
async def test_turn_change_during_read_cannot_publish(db, tmp_path):
    context = {'mode': 'pi', 'session_id': 'default', 'thread_id': 1, 'turn_id': 'a', 'agent_id': 'default', 'receipts': {}}
    def change(*args, **kwargs):
        attachments.active = {**context, 'turn_id': 'b'}
        return 'chart.png', 'image/png', png(), None, {'kind': 'image'}
    with patch.object(attachments, 'active', context), patch.object(attachments, 'read_attachment_file', change), \
         patch.object(attachments, 'get_db', AsyncMock(return_value=db)), patch.object(db, 'create_media', AsyncMock()) as store:
        with pytest.raises(PermissionError):
            await attachments.publish_file({'path': 'chart.png', 'request_id': 'call'}, 'pi')
        store.assert_not_awaited()


@pytest.mark.asyncio
async def test_attachment_transport_and_acp_mcp(aiohttp_client, db, tmp_path):
    # Resolve the runtime module used by the route despite old test modules that
    # intentionally purge sys.modules while collecting isolated Pi client tests.
    from importlib import import_module
    module = import_module('vibes.agent_attachments')
    root = await db.create_interaction({'type': 'user_message', 'content': 'attach', 'session_id': 'default'})
    (tmp_path / 'chart.png').write_bytes(png())
    context = {'mode': 'acp', 'session_id': 'default', 'thread_id': root, 'turn_id': 'a', 'agent_id': 'default', 'receipts': {}}
    app = web.Application()
    pi_tools.setup_routes(app)
    client = await aiohttp_client(app)
    url = str(client.make_url('/internal/agent-tools/attach-file'))
    token = module.acp_token('default')
    with patch.object(module, 'active', context), patch.object(module, 'get_db', AsyncMock(return_value=db)), \
         patch.object(module.Path, 'cwd', return_value=tmp_path):
        payload = {'path': 'chart.png', 'request_id': 'transport'}
        assert (await client.post('/internal/agent-tools/attach-file', json=payload)).status == 403
        assert (await client.post('/internal/agent-tools/attach-file', json=payload, headers={'Origin': 'http://evil', 'Authorization': 'Bearer ' + token})).status == 403
        server = MessagesMCP(MessageTools(db._connection, session_id='default'), attachment_url=url, attachment_token=token)
        listing = await server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        assert 'attach_file' in [tool['name'] for tool in listing['result']['tools']]
        result = await server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'attach_file', 'arguments': payload}})
        assert 'result' in result, result
        assert not result['result'].get('isError'), result
        text = json.dumps(result)
        assert 'attachment:' in text and 'base64' in text  # small explanatory text, no image bytes
        assert len(text) < 2000
        wrong = module.acp_token('another-session')
        response = await client.post('/internal/agent-tools/attach-file', json=payload, headers={'Authorization': 'Bearer ' + wrong})
        assert response.status == 403
        read_only = MessagesMCP(MessageTools(db._connection, workspace_access=True), attachment_url=url, attachment_token=token)
        listing = await read_only.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
        assert 'attach_file' not in [tool['name'] for tool in listing['result']['tools']]


@pytest.mark.asyncio
async def test_acp_attachment_only_stdio_without_message_read_grant(tmp_path):
    import sys
    from vibes.acp_client import _messages_mcp_servers
    with patch('vibes.acp_client.get_config') as config:
        config.return_value.acp_messages_enabled = False
        config.return_value.port = 8876
        descriptor = _messages_mcp_servers('private')[0]
    assert descriptor['name'] == 'vibes-attachments'
    assert '--attachments-only' in descriptor['args']
    env = {**os.environ, **{entry['name']: entry['value'] for entry in descriptor['env']}}
    # The fixture token only enables registration; no HTTP call or media write.
    env['VIBES_ATTACHMENT_URL'] = 'http://127.0.0.1:1/internal/agent-tools/attach-file'
    process = await asyncio.create_subprocess_exec(sys.executable, *descriptor['args'], env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await process.communicate(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}).encode() + b'\n')
    assert process.returncode == 0, err
    listed = json.loads(out)['result']['tools']
    assert [tool['name'] for tool in listed] == ['attach_file']
    assert not listed[0]['annotations']['readOnlyHint']


@pytest.mark.asyncio
async def test_acp_native_store_media_uses_same_publisher(tmp_path):
    from vibes import acp_client
    with patch('vibes.agent_attachments.publish_file', AsyncMock(return_value={'text': 'Attached', 'media_id': 42})) as publish:
        result = await acp_client._build_store_media_result({'path': 'chart.png'})
    assert publish.await_args.args[1:] == ('acp', acp_client._state.chat_id)
    assert result['content'][0]['type'] == 'text'
    assert '42' in result['content'][0]['text']
