import asyncio
import importlib
import json
import sys

import pytest

MessagesMCP = importlib.import_module('vibes.messages_mcp').MessagesMCP
MessageTools = importlib.import_module('vibes.message_tools').MessageTools


@pytest.mark.asyncio
async def test_discovery_and_reject_scope_escalation(db):
    server = MessagesMCP(MessageTools(db._connection, thread_id=1))
    def req(method, params=None):
        return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}
    assert (await server.handle(req('tools/list')))['result']['tools']
    assert (await server.handle(req('initialize', {'protocolVersion': '2024-11-05'})))['result']['protocolVersion'] == '2024-11-05'
    assert (await server.handle(req('tools/list')))['result']['tools'][0]['name'] == 'messages'
    assert 'error' in await server.handle(req('tools/call', {'name': 'messages', 'arguments': {'action': 'search', 'query': 'test', 'workspace_access': True}}))
    assert (await server.handle(req('resources/list')))['result']['resources'] == []


@pytest.mark.asyncio
async def test_real_stdio_process_and_thread_scope(db):
    root = await db.create_interaction({'type': 'user', 'content': 'visible'})
    hidden = await db.create_interaction({'type': 'user', 'content': 'hidden'})
    process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'vibes.messages_mcp',
        '--database', db.db_path, '--thread-id', str(root),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        async def call(method, params):
            process.stdin.write((json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}) + '\n').encode())
            await process.stdin.drain()
            return json.loads(await asyncio.wait_for(process.stdout.readline(), 5))
        await call('initialize', {'protocolVersion': '2025-06-18'})
        assert (await call('tools/list', {}))['result']['tools']
        result = await call('tools/call', {'name': 'messages', 'arguments': {'action': 'get', 'row_ids': [root, hidden]}})
        data = json.loads(result['result']['content'][0]['text'])
        assert [m['row_id'] for m in data['messages']] == [root]
        process.stdin.close()
        await asyncio.wait_for(process.wait(), 5)
        assert process.returncode == 0
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
