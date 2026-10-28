"""Owner-scoped shell preparation; no provider process is needed."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock

from vibes.db import Database
from vibes.routes import shell_tools
from vibes.secure.keychain import stores


@pytest.mark.asyncio
async def test_shell_preparation_requires_local_active_owner_and_preserves_no_secret_results(tmp_path, monkeypatch):
    from vibes import agent_attachments

    db = Database(str(tmp_path / 'bridge.db'))
    await db.connect()
    monkeypatch.setattr(shell_tools, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setenv('VIBES_KEYCHAIN_KEY_PATH', str(tmp_path / 'key'))
    monkeypatch.delenv('VIBES_KEYCHAIN_MASTER_PASSWORD', raising=False)
    keychain, environment = stores(db)
    await keychain.save('BRIDGE_SECRET', 'secret-value')
    await environment.set('BRIDGE_OVERRIDE', 'stored')
    owner = {'mode': 'pi', 'session_id': 'session-a'}

    def resolve(token):
        if token != 'valid':
            raise PermissionError('Invalid token')
        return 'pi', 'session-a'

    monkeypatch.setattr(agent_attachments, 'resolve_token', resolve)
    monkeypatch.setattr(agent_attachments, 'active_for', lambda session: owner)
    app = web.Application()
    shell_tools.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        path = '/internal/agent-tools/shell-prepare'
        payload = {'command': 'echo $BRIDGE_SECRET'}
        headers = {'Authorization': 'Bearer valid'}
        assert (await client.post(path, json=payload)).status == 403
        assert (await client.post(path, json=payload, headers={**headers, 'Origin': 'http://localhost'})).status == 403
        result = await client.post(path, json=payload, headers=headers)
        assert result.status == 200
        assert result.headers['Cache-Control'] == 'no-store'
        plan = await result.json()
        assert plan['env']['BRIDGE_SECRET'] == 'secret-value'
        assert plan['env']['BRIDGE_OVERRIDE'] == 'stored'
        assert plan['shell_kind'] == 'posix'
        assert 'VIBES_KEYCHAIN_KEY_PATH' not in plan['env']
        assert (await client.post(path, json={'command': 1}, headers=headers)).status == 400
        assert (await client.post(path, json={**payload, 'session_id': 'foreign'}, headers=headers)).status == 400
        from vibes.messages_mcp import MessagesMCP
        server = MessagesMCP(None, attachment_url=str(client.make_url('/internal/agent-tools/attach-file')).replace('localhost', '127.0.0.1'),
                             attachment_token='valid', attachment_session='session-a')
        listing = await server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        assert 'bash' in [tool['name'] for tool in listing['result']['tools']]
        result = await server.bash('printf "%s:%s" "$BRIDGE_SECRET" "$BRIDGE_OVERRIDE"')
        assert result == {'stdout': 'secret-value:stored', 'exit_code': 0}
        # Exercise the actual ACP-advertised MCP protocol in an independent process.
        import asyncio
        import json
        import os
        import sys
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'vibes.messages_mcp', '--attachments-only', '--session-id', 'session-a',
            env={**os.environ, 'VIBES_ATTACHMENT_URL': server.attachment_url, 'VIBES_ATTACHMENT_TOKEN': 'valid'},
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            request = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                'name': 'bash', 'arguments': {'command': 'printf "%s" "$BRIDGE_OVERRIDE"'},
            }}
            process.stdin.write((json.dumps(request) + '\n').encode())
            await process.stdin.drain()
            response = json.loads(await asyncio.wait_for(process.stdout.readline(), 5))
            assert json.loads(response['result']['content'][0]['text']) == {'stdout': 'stored', 'exit_code': 0}
        finally:
            process.stdin.close()
            try:
                await asyncio.wait_for(process.wait(), 5)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
        assert (await client.post('/internal/agent-tools/shell', json={**payload, 'timeout': True}, headers=headers)).status == 400
        monkeypatch.setattr(agent_attachments, 'active_for', lambda session: None)
        assert (await client.post(path, json=payload, headers=headers)).status == 403
        calls = 0

        def changed_owner(session):
            nonlocal calls
            calls += 1
            return owner if calls <= 2 else None

        monkeypatch.setattr(agent_attachments, 'active_for', changed_owner)
        assert (await client.post(path, json=payload, headers=headers)).status == 403
        calls = 0
        monkeypatch.setattr(agent_attachments, 'active_for', lambda session: owner)
        running = asyncio.create_task(client.post('/internal/agent-tools/shell', json={
            'command': 'sleep 60', 'timeout': 30,
        }, headers=headers))
        await asyncio.sleep(0.1)
        monkeypatch.setattr(agent_attachments, 'active_for', lambda session: None)
        stopped = await asyncio.wait_for(running, 2)
        assert stopped.status == 403
    finally:
        await client.close()
        await db.close()
