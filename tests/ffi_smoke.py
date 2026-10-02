"""Opt-in native smoke. Run in a fresh isolated process, never in production.

Set COPILOT_CLI_PATH to a provisioned SDK-compatible runtime entrypoint and
VIBES_FFI_SMOKE_ROOT to an empty owned directory. No authentication/session/model.
"""
import asyncio
import json
import os
from pathlib import Path
import sys

root = os.environ.get('VIBES_FFI_SMOKE_ROOT')
runtime = os.environ.get('COPILOT_CLI_PATH')
if not root or not runtime:
    raise SystemExit('Explicit smoke root and provisioned runtime required')
root = Path(root).absolute()
root.mkdir(parents=True, exist_ok=True)
if any(root.iterdir()):
    raise SystemExit('Smoke root must be empty')
keep = {k: v for k, v in os.environ.items() if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT'}}
os.environ.clear()
os.environ.update(keep)
os.environ.update(HOME=str(root), USERPROFILE=str(root), LOCALAPPDATA=str(root/'local'),
    APPDATA=str(root/'roaming'), TEMP=str(root), TMP=str(root),
    COPILOT_CLI_PATH=runtime, COPILOT_SKIP_CLI_DOWNLOAD='1', COPILOT_DISABLE_KEYTAR='1',
    VIBES_DEFAULT_AGENT='copilot-ffi', VIBES_COPILOT_USE_LOGGED_IN_USER='false',
    VIBES_COPILOT_STATE_DIR=str(root/'state'), VIBES_DB_PATH=str(root/'vibes.db'),
    XDG_CONFIG_HOME=str(root/'config'))
os.chdir(root)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from vibes.copilot_client import CopilotBackend  # noqa: E402


async def main():
    backend = CopilotBackend()
    await backend.start()
    try:
        assert backend.status()['ready']
        assert backend.status()['transport'] == 'ffi'
        for _ in range(10):
            await backend.client.ping('vibes-ffi-smoke')
        checks = {'passed': True, 'status': backend.status(), 'sessionsCreated': 0, 'modelCalls': 0}
        if '--session' in sys.argv:
            from vibes.db import init_db, close_db, get_db
            from vibes.sessions import SessionStore
            from vibes.config import get_config
            get_config().copilot_model = 'gpt-5.4'
            await init_db(str(root/'vibes.db'))
            try:
                store = SessionStore(await get_db())
                session = await asyncio.wait_for(backend._session('default', store), 20)
                checks['sessionsCreated'] = 1
                assert await store.backend_binding('default', 'copilot-ffi') is None
                checks['emptySessionUnboundVerified'] = True
                if '--resume' in sys.argv:
                    # Diagnostic negative control: deliberately bind an empty
                    # native session to reproduce runtime 1.0.85's resume failure.
                    saved_id = session.session_id
                    await store.bind_backend('default', 'copilot-ffi', saved_id)
                    await session.log('Synthetic local persistence marker; no model request')
                    from copilot.generated.rpc import SessionsSaveRequest
                    await backend.client.rpc.sessions.save(SessionsSaveRequest(session_id=saved_id))
                    await session.disconnect()
                    await backend.stop()
                    await backend.start()
                    resumed = await asyncio.wait_for(backend._session('default', store), 20)
                    assert resumed.session_id == saved_id
                    checks['resumeAfterHostRestartVerified'] = True
            finally:
                await close_db()
        print(json.dumps(checks))
    finally:
        await backend.stop()
    assert not backend.status()['ready']


asyncio.run(main())
