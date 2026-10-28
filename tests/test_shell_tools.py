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
        monkeypatch.setattr(agent_attachments, 'active_for', lambda session: None)
        assert (await client.post(path, json=payload, headers=headers)).status == 403
        calls = 0

        def changed_owner(session):
            nonlocal calls
            calls += 1
            return owner if calls <= 2 else None

        monkeypatch.setattr(agent_attachments, 'active_for', changed_owner)
        assert (await client.post(path, json=payload, headers=headers)).status == 403
    finally:
        await client.close()
        await db.close()
