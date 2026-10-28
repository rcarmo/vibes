"""Shell execution with stored overrides and command-scoped keychain injection."""

import asyncio
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
    entries = {}

    async def entry(name):
        if name not in entries:
            entries[name] = await keychain.reveal(name, master_password=keychain.master_password)
        return entries[name]

    injected = []
    for variable in referenced_names(command):
        if variable not in mapping or variable in effective:
            continue
        effective[variable] = (await entry(mapping[variable]))['secret']
        injected.append(variable)

    # Classic's explicit placeholder contract is literal substitution, even inside quotes.
    # Prefer variable references for credentials containing shell syntax.
    for name in placeholder_names(command):
        await entry(name)
    text = resolve_placeholders(command, entries.get)
    return {'text': text, 'env': effective, 'injected': injected, 'shell': shell}


async def run_shell(command: str, keychain, environment, shell_path: str | None = None,
                    env=None, platform: str | None = None, cwd=None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    plan = await prepare(command, keychain, environment, shell_path=shell_path, env=env, platform=platform)
    process = await asyncio.create_subprocess_exec(
        *plan['shell']['argv'](plan['text']), stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env=plan['env'], cwd=cwd, start_new_session=os.name != 'nt',
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
