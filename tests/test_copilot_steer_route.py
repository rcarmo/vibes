import pytest
from types import SimpleNamespace


@pytest.mark.asyncio
async def test_unsupported_ffi_steer_is_rejected_before_persistence(monkeypatch):
    from vibes.routes import agents
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda agent: 'copilot-ffi')
    async def unexpected_db():
        raise AssertionError('Rejected steering must not persist or enqueue')
    monkeypatch.setattr(agents, 'get_db', unexpected_db)
    response = await agents._send_message(SimpleNamespace(match_info={'agent_id': 'default'}), {'content': 'steer now', 'mode': 'steer'})
    assert response.status == 409
    assert b'Native Copilot steering is not enabled' in response.body

@pytest.mark.asyncio
async def test_unsupported_queued_ffi_steer_preserves_item(db, monkeypatch):
    from unittest.mock import AsyncMock
    from vibes.routes import agents
    from vibes.followup_store import FollowupStore
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda agent: 'copilot-ffi')
    monkeypatch.setattr(agents, 'get_db', AsyncMock(return_value=db))
    root = await db.create_interaction({'type': 'user', 'content': 'queued source'})
    store = FollowupStore(db)
    item = await store.enqueue(thread_id=root, agent_id='default', message_id=root, content='preserve')
    async def json():
        return {'row_id': item['row_id']}
    response = await agents.steer_queue_item(SimpleNamespace(json=json))
    assert response.status == 409
    assert b'preserved' in response.body
    rows = await store.list()
    assert len(rows) == 1 and rows[0]['row_id'] == item['row_id'] and rows[0]['state'] == 'pending'
