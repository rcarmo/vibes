"""Backend shell contract; no live provider or browser acceptance is implied."""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from vibes.db import Database
from vibes.secure import aead
from vibes.secure.environment_overrides import EnvironmentStore
from vibes.secure.keychain import KeychainStore
from vibes.secure.shell_exec import prepare, run_shell


@pytest_asyncio.fixture
async def stores(tmp_path):
    db = Database(str(tmp_path / 'shell.db'))
    await db.connect()
    try:
        keychain = KeychainStore(db, master_password='master')
        environment = EnvironmentStore(db, keychain=keychain, base_env={'PATH': os.defpath})
        yield keychain, environment
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_selective_retrieval_collision_and_precedence(stores, monkeypatch):
    keychain, environment = stores
    await keychain.save('fixtures/lower-1', 'slash')
    await keychain.save('fixtures.lower.1', 'dot')
    await keychain.save('lower', 'lower-case')
    reveal = AsyncMock(wraps=keychain.reveal_many)
    monkeypatch.setattr(keychain, 'reveal_many', reveal)
    plan = await prepare('echo $FIXTURES_LOWER_1 $UNKNOWN $LOWER', keychain, environment)
    assert plan['env']['FIXTURES_LOWER_1'] == 'dot'
    assert 'lower' not in plan['env']
    assert reveal.await_count == 1
    reveal.assert_awaited_once_with(['fixtures.lower.1'], master_password='master')
    reveal.reset_mock()
    await prepare('env', keychain, environment)
    await prepare('echo $FIXTURES_LOWER_1', keychain, environment, env={'FIXTURES_LOWER_1': 'inherited'})
    assert all(call.args[0] == [] for call in reveal.await_args_list)
    assert all(value not in repr(plan['injected']) for value in ['slash', 'dot', 'lower-case'])


@pytest.mark.asyncio
async def test_key_derivation_is_command_scoped_and_empty_commands_read_no_key(stores, monkeypatch):
    keychain, environment = stores
    await keychain.save('FIRST', 'one')
    await keychain.save('SECOND', 'two')
    from unittest.mock import Mock
    derive = Mock(wraps=aead.derive_key)
    decrypt = Mock(wraps=aead.decrypt)
    monkeypatch.setattr(aead, 'derive_key', derive)
    monkeypatch.setattr(aead, 'decrypt', decrypt)
    await prepare('env', keychain, environment)
    derive.assert_not_called()
    decrypt.assert_not_called()
    command = 'echo $FIRST $SECOND keychain:FIRST'
    for _ in range(2):
        plan = await prepare(command, keychain, environment)
        assert plan['env']['FIRST'] == 'one' and plan['env']['SECOND'] == 'two'
    assert derive.call_count == 2  # One per command, no key cached between operations.
    assert decrypt.call_count == 6  # One key-check + exactly two selected entries each time.
    assert 'key' not in keychain.__dict__


@pytest.mark.asyncio
async def test_all_reference_syntaxes_and_config_credentials_are_filtered(stores):
    keychain, environment = stores
    await keychain.save('NAME', 'value')
    for command in ["echo '$NAME'", '# ${NAME}', 'echo $env:NAME', 'echo %NAME%']:
        plan = await prepare(command, keychain, environment, env={
            'VIBES_KEYCHAIN_MASTER_PASSWORD': 'master', 'VIBES_KEYCHAIN_KEY_PATH': '/private/key',
        })
        assert plan['env']['NAME'] == 'value'
        assert 'VIBES_KEYCHAIN_MASTER_PASSWORD' not in plan['env']
        assert 'VIBES_KEYCHAIN_KEY_PATH' not in plan['env']


@pytest.mark.asyncio
async def test_placeholders_resolve_before_execution_and_fail_closed(stores, tmp_path):
    keychain, environment = stores
    await keychain.save('fixtures/entry', 'secret', username='user')
    for field, expected in [('', 'secret'), (':secret', 'secret'), (':password', 'secret'),
                            (':token', 'secret'), (':username', 'user'), (':user', 'user')]:
        plan = await prepare(f"printf '%s' 'keychain:fixtures/entry{field}'", keychain, environment)
        assert plan['text'] == f"printf '%s' '{expected}'"
    await keychain.save('no_username', 'value')
    for placeholder in ['keychain:missing', 'keychain:no_username:username', 'keychain:no_username:unknown']:
        with pytest.raises((LookupError, ValueError)):
            await run_shell(f'touch must-not-run; echo {placeholder}', keychain, environment, cwd=tmp_path)
        assert not (tmp_path / 'must-not-run').exists()


@pytest.mark.asyncio
async def test_overrides_apply_to_next_commands_and_clear_restores_inheritance(stores, tmp_path):
    keychain, environment = stores
    environment.base_env['VALUE'] = 'inherited'
    await environment.set('VALUE', 'first')
    result = await run_shell('printf "%s" "$VALUE"; pwd', keychain, environment, cwd=tmp_path)
    assert result['stdout'] == f'first{tmp_path}\n'
    assert set(result) == {'stdout', 'exit_code'}
    await environment.set('VALUE', 'second')
    assert (await run_shell('printf "%s" "$VALUE"', keychain, environment))['stdout'] == 'second'
    await environment.clear('VALUE')
    assert (await run_shell('printf "%s" "$VALUE"', keychain, environment))['stdout'] == 'inherited'


@pytest.mark.asyncio
async def test_output_is_bounded_and_pipe_is_drained(stores):
    keychain, environment = stores
    result = await run_shell('head -c 700000 /dev/zero', keychain, environment)
    assert result['exit_code'] == 0
    assert len(result['stdout'].encode()) < 513 * 1024
    assert result['stdout'].endswith('[output truncated at 512 KiB]\n')


@pytest.mark.asyncio
async def test_unstartable_candidate_falls_back_but_configured_shell_does_not(stores, tmp_path):
    if os.name == 'nt':
        pytest.skip('POSIX executable fixture')
    keychain, environment = stores
    invalid = tmp_path / 'not-a-shell'
    invalid.write_text('invalid executable format')
    invalid.chmod(0o700)
    environment.base_env['SHELL'] = str(invalid)
    assert (await run_shell('printf success', keychain, environment))['stdout'] == 'success'
    with pytest.raises(OSError):
        await run_shell('printf must-not-run', keychain, environment, shell_path=str(invalid))
    with pytest.raises(FileNotFoundError):
        await run_shell('printf must-not-run', keychain, environment, cwd=tmp_path / 'missing')


@pytest.mark.asyncio
async def test_timeout_and_cancellation_stop_posix_process_group(stores, tmp_path):
    if os.name == 'nt':
        pytest.skip('POSIX process groups; Windows runtime acceptance is not claimed')
    keychain, environment = stores
    pid_file = tmp_path / 'child.pid'
    command = 'sleep 60 & echo $! > child.pid; wait'
    result = await run_shell(command, keychain, environment, cwd=tmp_path, timeout=0.1)
    assert result['exit_code'] == 124
    pid = int(pid_file.read_text())
    task = asyncio.create_task(run_shell(command, keychain, environment, cwd=tmp_path))
    pid_file.unlink()
    for _ in range(200):
        if pid_file.exists() and pid_file.read_text().strip():
            break
        await asyncio.sleep(0.01)
    else:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        pytest.fail('shell did not start')
    second_pid = int(pid_file.read_text())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    for child in [pid, second_pid]:
        # A killed orphan can briefly remain as a zombie until PID 1 reaps it.
        stat_path = Path(f'/proc/{child}/stat')
        try:
            state = stat_path.read_text().split()[2]
        except FileNotFoundError:
            # Reaping can happen between exists() and read(); disappearance is success.
            with pytest.raises(ProcessLookupError):
                os.kill(child, 0)
        else:
            assert state == 'Z'
