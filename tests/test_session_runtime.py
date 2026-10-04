import asyncio

import pytest

from vibes.session_runtime import SessionRuntimes


def test_identity_and_passive_lookup():
    runtimes = SessionRuntimes(dict)
    assert runtimes.existing('a') is None
    assert runtimes.snapshot() == ()
    a = runtimes.get('a')
    assert runtimes.get('a') is a
    assert runtimes.get('b') is not a
    with pytest.raises(ValueError):
        runtimes.get(' ')


def test_nested_binding_restores_owner_after_exception():
    runtimes = SessionRuntimes(dict)
    default = runtimes.current()
    with runtimes.bind('a') as a:
        with pytest.raises(RuntimeError):
            with runtimes.bind('b') as b:
                assert runtimes.current() is b
                raise RuntimeError()
        assert runtimes.current() is a
    assert runtimes.current() is default


@pytest.mark.asyncio
async def test_simultaneous_tasks_and_children_keep_their_owner():
    runtimes = SessionRuntimes(dict)
    entered = {chat: asyncio.Event() for chat in ('a', 'b')}
    release = asyncio.Event()

    async def child(owner):
        await release.wait()
        assert runtimes.current() is owner

    async def run(chat):
        with runtimes.bind(chat) as owner:
            owner['chat'] = chat
            task = asyncio.create_task(child(owner))
            entered[chat].set()
            await release.wait()
            assert runtimes.current()['chat'] == chat
            await task

    tasks = [asyncio.create_task(run(chat)) for chat in entered]
    try:
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered.values())), 1)
        assert runtimes.existing('a') is not runtimes.existing('b')
    finally:
        release.set()
        await asyncio.gather(*tasks)
    assert runtimes.current() is runtimes.get('default')


@pytest.mark.asyncio
async def test_cancelled_binding_does_not_change_other_owner():
    runtimes = SessionRuntimes(dict)
    entered = asyncio.Event()

    async def run():
        with runtimes.bind('a'):
            entered.set()
            await asyncio.Future()

    with runtimes.bind('b') as b:
        task = asyncio.create_task(run())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtimes.current() is b
    assert runtimes.existing('a') is not b


@pytest.mark.asyncio
async def test_client_callbacks_reach_new_chat_and_shutdown_visits_all_owners():
    from unittest.mock import AsyncMock, patch
    from vibes import acp_client as acp, pi_client as pi

    for client in (pi, acp):
        callback = AsyncMock()
        client.set_request_callback(callback)
        with client._runtimes.bind('new-callback-chat'):
            assert client._state.request_callback is callback
        client.set_request_callback(None)

    pi_owners, acp_owners = [], []

    async def stop_pi():
        pi_owners.append(pi._runtimes.current())

    async def stop_acp():
        acp_owners.append(acp._runtimes.current())

    with patch.object(pi, '_stop_current_pi_agent', side_effect=stop_pi), \
         patch.object(acp, 'stop_agent', side_effect=stop_acp):
        await pi.stop_pi_agent()
        await acp.stop_all_agents()
    assert pi_owners == [state for _, state in pi._runtimes.snapshot()]
    assert acp_owners == [state for _, state in acp._runtimes.snapshot()]


@pytest.mark.asyncio
async def test_real_pi_process_ownership_and_independent_stop(tmp_path):
    import sys
    from types import SimpleNamespace
    from unittest.mock import patch
    from vibes import pi_client as pi

    script = tmp_path / 'idle_rpc.py'
    script.write_text('import time\ntime.sleep(60)\n')
    config = SimpleNamespace(effective_pi_command=lambda: f'{sys.executable} {script}', port=8765)
    processes = []
    with patch.object(pi, 'get_config', return_value=config):
        try:
            for chat in ('process-a', 'process-b'):
                with pi._runtimes.bind(chat):
                    assert await pi.start_pi_agent()
                    processes.append(pi._state.agent_proc)
            a, b = processes
            assert a.pid != b.pid
            assert a.returncode is None and b.returncode is None
            with pi._runtimes.bind('process-a'):
                await pi._stop_current_pi_agent()
            assert a.returncode is not None
            assert b.returncode is None
            with pi._runtimes.bind('process-b'):
                assert pi.is_pi_running()
        finally:
            await pi.stop_pi_agent()
    assert all(process.returncode is not None for process in processes)


@pytest.mark.asyncio
async def test_real_acp_processes_survive_other_owner_stop(tmp_path):
    import sys
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from vibes import acp_client as acp

    script = tmp_path / 'idle_acp.py'
    script.write_text('import time\ntime.sleep(60)\n')
    config = SimpleNamespace(acp_agent=f'{sys.executable} {script}', acp_throttle_rps=0)
    processes = []
    with patch.object(acp, 'get_config', return_value=config), \
         patch.object(acp, '_messages_mcp_servers', return_value=[]), \
         patch.object(acp, '_send_request', AsyncMock(return_value={'sessionId': 'synthetic'})):
        try:
            for chat in ('acp-process-a', 'acp-process-b'):
                with acp._runtimes.bind(chat):
                    assert await acp.start_agent()
                    processes.append(acp._state.agent_proc)
            a, b = processes
            assert a.pid != b.pid
            with acp._runtimes.bind('acp-process-a'):
                await acp.stop_agent()
            assert a.returncode is not None and b.returncode is None
        finally:
            await acp.stop_all_agents()
    assert all(process.returncode is not None for process in processes)
