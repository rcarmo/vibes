import asyncio
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from vibes.db import Database
from vibes.plans import PlanStore, PlanConflict, normalize_markdown, apply_plan_action
from vibes.sessions import SessionStore
from vibes.routes import plans


@pytest.mark.asyncio
async def test_plan_storage_revision_restart_and_session_isolation(tmp_path):
    path = str(tmp_path / 'plans.db')
    db = Database(path)
    await db.connect()
    other = await SessionStore(db).create('Other')
    store = PlanStore(db)
    assert (await store.get('default'))['revision'] == 0
    saved = await store.apply('default', {'action': 'write', 'markdown': 'Notes\n- [-] A\n- [-] B', 'expected_revision': 0})
    assert saved['markdown'] == 'Notes\n- [-] A\n- [ ] B'
    assert saved['revision'] == 1
    with pytest.raises(PlanConflict):
        await store.apply('default', {'action': 'write', 'markdown': 'stale', 'expected_revision': 0})
    assert (await store.get(other['id']))['revision'] == 0
    await db.close()
    await db.connect()
    assert (await PlanStore(db).get('default'))['markdown'] == saved['markdown']
    await db.close()


@pytest.mark.asyncio
async def test_atomic_plan_cas_across_connections(tmp_path):
    path = str(tmp_path / 'plans.db')
    a, b = Database(path), Database(path)
    await a.connect()
    await b.connect()
    await PlanStore(a).apply('default', {'action': 'write', 'markdown': 'initial'})
    results = await asyncio.gather(*[PlanStore(db).apply('default', {'action': 'write', 'markdown': text, 'expected_revision': 1}) for db, text in [(a, 'a'), (b, 'b')]], return_exceptions=True)
    assert sum(isinstance(result, PlanConflict) for result in results) == 1
    assert (await PlanStore(a).get('default'))['revision'] == 2
    await a.close()
    await b.close()


def test_plan_actions_are_bounded_preserve_prose_and_ignore_fenced_examples():
    markdown = 'Notes\n```md\n- [-] example\n```\n- [-] first\n- [-] second'
    assert normalize_markdown(markdown).endswith('- [-] first\n- [ ] second')
    edited = apply_plan_action(markdown, {'action': 'patch', 'patches': [{'operation': 'update', 'index': 1, 'status': 'completed'}, {'operation': 'update', 'match': 'second', 'status': 'in_progress'}]})
    assert edited.startswith('Notes\n```md\n- [-] example')
    assert edited.endswith('- [x] first\n- [-] second')
    assert apply_plan_action('Notes', {'action': 'edit', 'edits': [{'oldText': 'Notes', 'newText': 'New notes'}]}) == 'New notes'
    with pytest.raises(ValueError):
        apply_plan_action('A A', {'action': 'edit', 'edits': [{'oldText': 'A', 'newText': 'B'}]})
    for payload in [{'action': 'write', 'markdown': 'x' * (128 * 1024 + 1)}, {'action': 'patch', 'patches': [{'operation': 'remove', 'index': True}]}, {'action': 'update', 'plan': [{'step': 'a\nb'}]}, {'action': 'write', 'markdown': '', 'session_id': 'other'}]:
        with pytest.raises(ValueError):
            apply_plan_action('', payload)


@pytest.mark.asyncio
async def test_plan_browser_tool_roundtrip_conflict_scope_and_origin(tmp_path, monkeypatch):
    from importlib import import_module
    # Some Pi tests purge runtime modules during collection; patch the module used by the route.
    agent_attachments = import_module('vibes.agent_attachments')
    db = Database(str(tmp_path / 'plans.db'))
    await db.connect()
    other = await SessionStore(db).create('Other')
    async def get_db():
        return db
    events = []
    async def broadcast(name, value):
        events.append((name, value))
    monkeypatch.setattr(plans, 'get_db', get_db)
    monkeypatch.setattr(plans, 'broadcast_event', broadcast)
    monkeypatch.setattr(agent_attachments, 'active', {'mode': 'pi', 'session_id': 'default', 'turn_id': 'test'})
    app = web.Application()
    plans.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    headers = {'Authorization': 'Bearer ' + agent_attachments.PI_TOKEN}
    try:
        response = await client.post('/internal/agent-tools/plan', headers=headers, json={'action': 'write', 'markdown': '- [ ] Model step', 'expected_revision': 0})
        assert response.status == 200
        assert (await response.json())['revision'] == 1
        assert (await (await client.get('/sessions/default/plan')).json())['markdown'] == '- [ ] Model step'
        response = await client.put('/sessions/default/plan', json={'markdown': '- [x] Browser step', 'expected_revision': 1})
        assert response.status == 200
        response = await client.post('/internal/agent-tools/plan', headers=headers, json={'action': 'read'})
        assert (await response.json())['revision'] == 2
        stale = await client.post('/internal/agent-tools/plan', headers=headers, json={'action': 'write', 'markdown': 'stale', 'expected_revision': 1})
        assert stale.status == 409
        assert len(events) == 2
        assert events[-1][0] == 'plan_updated'
        assert events[-1][1]['session_id'] == 'default'
        assert (await PlanStore(db).get(other['id']))['revision'] == 0
        assert (await client.post('/internal/agent-tools/plan', headers={**headers, 'Origin': 'http://localhost'}, json={'action': 'read'})).status == 403
        assert (await client.post('/internal/agent-tools/plan', headers=headers, json={'action': 'read', 'session_id': other['id']})).status == 400
        monkeypatch.setattr(agent_attachments, 'active', None)
        assert (await client.post('/internal/agent-tools/plan', headers=headers, json={'action': 'read'})).status == 403
        assert (await client.put('/sessions/default/plan', json={'markdown': ''})).status == 400
        assert (await client.get('/sessions/unknown/plan')).status == 404
    finally:
        await client.close()
        await db.close()
