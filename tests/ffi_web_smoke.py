"""Short-lived loopback fixture with the real FFI host; no sessions or model calls."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

root = Path(tempfile.mkdtemp(prefix='vibes-ffi-web-'))
runtime = os.environ.get('COPILOT_CLI_PATH')
if not runtime:
    raise SystemExit('Provisioned runtime path required')
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
from aiohttp import web  # noqa: E402
from vibes.app import create_app  # noqa: E402


async def main():
    # Synthetic UI requests exercise actual status/SSE/response routes while the
    # native host stays idle. This fixture-only endpoint is never in production.
    from vibes.copilot_host import backend
    from vibes.config import get_config
    from vibes.db import get_db
    backend = backend.lane("default")
    tasks = []
    async def request_fixture(request):
        if backend.active:
            return web.json_response({'error':'busy'},status=409)
        db = await get_db()
        thread = await db.create_interaction({'type':'user_message','content':'Synthetic browser prompt'})
        turn = 'browser-'+str(thread)
        await db.begin_turn(turn,thread,'default')
        backend.active={'chat_id':'default','thread_id':thread,'turn_id':turn,'cancelled':False}
        get_config().permission_timeout = 2 if request.query.get('timeout') else 30
        async def decision():
            try:
                await backend._decision('Synthetic browser question',{},[{'optionId':'freeform'},{'optionId':'deny','name':'Cancel','kind':'reject_once'}])
            finally:
                backend.active=None
                await db.end_turn(turn)
        tasks.append(asyncio.create_task(decision()))
        return web.json_response({'turn_id':turn})
    app = create_app()
    app.router.add_post('/fixture/request', request_fixture)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    print(json.dumps({'port': port, 'root': str(root)}), flush=True)
    # stdin close/one line requests graceful cleanup, with an independent bound.
    try:
        await asyncio.wait_for(asyncio.to_thread(sys.stdin.readline), 60)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        await runner.cleanup()
        print(json.dumps({'stopped': True}), flush=True)


asyncio.run(main())
