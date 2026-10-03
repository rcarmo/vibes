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
async def test_unsupported_queued_ffi_steer_preserves_item(monkeypatch):
    from vibes.routes import agents
    monkeypatch.setattr(agents, '_resolve_agent_mode', lambda agent: 'copilot-ffi')
    monkeypatch.setattr(agents, 'find_followup', lambda row: {'agent_id': 'default', 'thread_id': 1, 'row_id': row})
    def unexpected_remove(*args):
        raise AssertionError('Unsupported steering must not remove queue item')
    monkeypatch.setattr(agents, 'remove_followup', unexpected_remove)
    async def json():
        return {'row_id': 1}
    response = await agents.steer_queue_item(SimpleNamespace(json=json))
    assert response.status == 409
    assert b'preserved' in response.body
