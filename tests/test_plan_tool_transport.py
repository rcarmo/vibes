"""Exercise registered model tools against the same HTTP/store used by the browser."""
import json
from importlib import import_module
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from vibes.db import Database
from vibes.plans import PlanStore
from vibes.routes import plans
from vibes.messages_mcp import MessagesMCP


@pytest.mark.asyncio
async def test_registered_acp_plan_calls_shared_api_without_history_read_grant(tmp_path, monkeypatch):
    owner = import_module('vibes.agent_attachments')
    db = Database(str(tmp_path / 'db.sqlite'))
    await db.connect()
    async def get_db():
        return db
    monkeypatch.setattr(plans, 'get_db', get_db)
    monkeypatch.setattr(owner, 'active', {'mode': 'acp', 'session_id': 'default', 'turn_id': 'fixture'})
    app = web.Application()
    plans.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        server = MessagesMCP(None, attachment_url=str(client.make_url('/internal/agent-tools/attach-file')),
                             attachment_token=owner.acp_token('default'), attachment_session='default')
        listed = await server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        tools = {tool['name']: tool for tool in listed['result']['tools']}
        assert 'messages' not in tools and 'plan' in tools
        async def call(arguments):
            return await server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'plan', 'arguments': arguments}})
        response = await call({'action': 'write', 'markdown': '- [ ] MCP step', 'expected_revision': 0})
        assert not response['result'].get('isError'), response
        assert (await PlanStore(db).get('default'))['revision'] == 1
        await PlanStore(db).apply('default', {'action': 'write', 'markdown': '- [x] Browser step', 'expected_revision': 1})
        response = await call({'action': 'read'})
        assert 'Browser step' in json.dumps(response)
        response = await call({'action': 'write', 'markdown': 'stale', 'expected_revision': 1})
        assert response.get('result', {}).get('isError') or response.get('error'), response
        assert (await PlanStore(db).get('default'))['markdown'] == '- [x] Browser step'
    finally:
        await client.close()
        await db.close()


def test_pi_extension_registers_plan_with_bounded_scope_free_schema():
    # Source contract complements runtime executor/HTTP checks; not live model evidence.
    text = (Path(__file__).parents[1] / 'src/vibes/extensions/pi-vibes-tools.ts').read_text()
    plan = text.split('name: "vibes_plan",', 1)[1].split('name: "vibes_messages",', 1)[0]
    assert 'expected_revision' in plan
    assert 'session_id' not in plan and 'chat_jid' not in plan
    assert '/internal/agent-tools/plan' in plan
    assert 'signal' in plan
