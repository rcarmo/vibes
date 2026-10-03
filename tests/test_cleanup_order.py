from types import SimpleNamespace
from unittest.mock import AsyncMock
import importlib

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize('pi', [True, False])
async def test_cleanup_drains_workers_before_stopping_backend(monkeypatch, pi):
    app = importlib.import_module('vibes.app')
    order = []
    async def drain():
        order.append('drain')
    async def stop():
        order.append('backend')
    monkeypatch.setattr(app, 'get_config', lambda: SimpleNamespace(default_agent='pi' if pi else 'acp', pi_enabled=pi))
    monkeypatch.setattr(app, 'stop_task_queue', drain)
    monkeypatch.setattr(app, 'stop_pi_agent' if pi else 'stop_acp_agent', stop)
    monkeypatch.setattr(app.agents, 'stop_ffi_dispatch', AsyncMock())
    monkeypatch.setattr(app.workspace, 'shutdown_workspace_manager', AsyncMock())
    monkeypatch.setattr(app, 'close_db', AsyncMock())
    await app.on_cleanup(None)
    assert order == ['drain', 'backend']


@pytest.mark.asyncio
@pytest.mark.parametrize('native_failure', [False, True])
async def test_ffi_cleanup_finishes_after_native_shutdown_failure(monkeypatch, native_failure):
    from unittest.mock import Mock
    app = importlib.import_module('vibes.app')
    from vibes.copilot_host import backend
    order = []
    async def native_stop(**kwargs):
        assert kwargs == {'permanent': True}
        order.append('native')
        if native_failure:
            raise RuntimeError('native failure')
    def step(name):
        async def run():
            order.append(name)
        return run
    monkeypatch.setattr(app, 'get_config', lambda: SimpleNamespace(default_agent='copilot-ffi', pi_enabled=False))
    monkeypatch.setattr(app.agents, 'close_ffi_admission', Mock(side_effect=lambda: order.append('close-admission')))
    monkeypatch.setattr(backend, 'stop', native_stop)
    monkeypatch.setattr(app.agents, 'stop_ffi_dispatch', step('dispatch'))
    monkeypatch.setattr(app, 'stop_task_queue', step('workers'))
    monkeypatch.setattr(app.workspace, 'shutdown_workspace_manager', step('workspace'))
    monkeypatch.setattr(app, 'close_db', step('database'))
    await app.on_cleanup(None)
    assert order == ['close-admission', 'native', 'dispatch', 'workers', 'workspace', 'database']
