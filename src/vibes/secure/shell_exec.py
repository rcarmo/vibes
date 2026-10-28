"""Shell execution with stored overrides and command-scoped keychain injection."""

import asyncio
import errno
import os
import signal

from . import shell_detect
from .environment_overrides import PRIVATE_VARIABLES
from .shell_secrets import placeholder_names, referenced_names, resolve_placeholders

DEFAULT_TIMEOUT = 30


async def prepare(command: str, keychain, environment, shell_path: str | None = None,
                  env=None, platform: str | None = None) -> dict:
    stored = await environment.overrides()
    effective = environment.effective_env(stored=stored, base=env)
    for variable in PRIVATE_VARIABLES:
        effective.pop(variable, None)
    shell = shell_detect.detect_shell(shell_path, env=effective, platform=platform)
    mapping = await keychain.variable_map()
    injected = [variable for variable in referenced_names(command)
                if variable in mapping and variable not in effective]
    names = [mapping[variable] for variable in injected] + placeholder_names(command)
    entries = await keychain.reveal_many(names, master_password=keychain.master_password)
    for variable in injected:
        effective[variable] = entries[mapping[variable]]['secret']

    # Classic's explicit placeholder contract is literal substitution, even inside quotes.
    # Prefer variable references for credentials containing shell syntax.
    text = resolve_placeholders(command, entries.get)
    return {'text': text, 'env': effective, 'injected': injected, 'shell': shell}


async def run_shell(command: str, keychain, environment, shell_path: str | None = None,
                    env=None, platform: str | None = None, cwd=None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    plan = await prepare(command, keychain, environment, shell_path=shell_path, env=env, platform=platform)
    return await run_prepared(plan, shell_path=shell_path, platform=platform, cwd=cwd, timeout=timeout)


async def run_prepared(plan: dict, shell_path=None, platform=None, cwd=None,
                       timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Execute a private preparation result without copying it into output or logs."""
    failed = set()
    while True:
        try:
            process = await asyncio.create_subprocess_exec(
                *plan['shell']['argv'](plan['text']), stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                env=plan['env'], cwd=cwd, start_new_session=os.name != 'nt',
            )
            break
        except OSError as exc:
            # Retry only failures before a child command can run. Never replay a command
            # that started, returned nonzero, timed out or was cancelled.
            if shell_path or exc.errno not in {errno.ENOENT, errno.ENOEXEC}:
                raise
            if cwd is not None and not os.path.isdir(cwd):
                raise
            failed.add(plan['shell']['path'])
            plan['shell'] = shell_detect.detect_shell(
                env=plan['env'], platform=platform,
                can_start=lambda path: path not in failed and os.access(path, os.X_OK),
            )

    async def stop():
        try:
            if os.name == 'nt':
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.communicate()

    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        await stop()
        return {'stdout': f'[timed out after {timeout}s]', 'exit_code': 124}
    except asyncio.CancelledError:
        await stop()
        raise
    return {'stdout': (stdout or b'').decode('utf-8', errors='replace'),
            'exit_code': process.returncode}
