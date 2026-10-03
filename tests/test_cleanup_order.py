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
