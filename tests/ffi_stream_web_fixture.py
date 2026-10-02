"""Real FFI -> HTTP routes -> SSE -> browser fixture. Loopback fake inference only."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace

root = Path(tempfile.mkdtemp(prefix='vibes-stream-web-'))
runtime = os.environ.get('COPILOT_CLI_PATH')
if not runtime:
    raise SystemExit('Explicit provisioned native runtime required')
keep = {k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT'}}
os.environ.clear()
os.environ.update(keep)
os.environ.update(HOME=str(root), USERPROFILE=str(root), APPDATA=str(root/'roaming'), LOCALAPPDATA=str(root/'local'),
    TEMP=str(root), TMP=str(root), COPILOT_CLI_PATH=runtime, COPILOT_SKIP_CLI_DOWNLOAD='1', COPILOT_DISABLE_KEYTAR='1',
    VIBES_DEFAULT_AGENT='copilot-ffi', VIBES_COPILOT_MODEL='gpt-4.1', VIBES_COPILOT_USE_LOGGED_IN_USER='false',
    VIBES_COPILOT_STATE_DIR=str(root/'native'), VIBES_DB_PATH=str(root/'vibes.db'), XDG_CONFIG_HOME=str(root/'config'))
os.chdir(root)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from aiohttp import web  # noqa: E402
from vibes.app import create_app  # noqa: E402
from vibes.copilot_host import backend  # noqa: E402


async def main():
    step = asyncio.Event()
    calls = []
    chunks = ['A ', 'real ', 'stream ', 'must ', 'accumulate.\n'] + [f'Line {i}\n' for i in range(1,12)] + ['Expanded ', 'words ', 'remain ', 'together.']
    async def model(request):
        body = await request.json()
        calls.append({'model':body.get('model'),'stream':body.get('stream')})
        response = web.StreamResponse(headers={'Content-Type':'text/event-stream'})
        await response.prepare(request)
        for index, text in enumerate(chunks):
            if index:
                await step.wait()
                step.clear()
            delta = {'content':text}
            packet = {'id':'stream-fixture','object':'chat.completion.chunk','created':int(time.time()),'model':'gpt-4.1',
                      'choices':[{'index':0,'delta':delta,'finish_reason':None}]}
            await response.write(('data: '+json.dumps(packet)+'\n\n').encode())
        await step.wait()
        await response.write(b'data: {"id":"stream-fixture","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        return response
    inference = web.Application()
    inference.router.add_post('/v1/chat/completions', model)
    ir = web.AppRunner(inference)
    await ir.setup()
    site = web.TCPSite(ir,'127.0.0.1',0)
    await site.start()
    provider = {'type':'openai','wire_api':'completions','base_url':f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/v1','api_key':'synthetic'}
    async def advance(request):
        step.set()
        return web.json_response({'ok':True})
    app = create_app()
    app.router.add_post('/fixture/step',advance)
    runner = web.AppRunner(app)
    await runner.setup()
    real = backend.client
    async def create(**kwargs):
        return await real.create_session(provider=provider,**kwargs)
    async def resume(sid,**kwargs):
        return await real.resume_session(sid,provider=provider,**kwargs)
    backend.client = SimpleNamespace(create_session=create,resume_session=resume,rpc=real.rpc,stop=real.stop)
    site = web.TCPSite(runner,'127.0.0.1',0)
    await site.start()
    print(json.dumps({'port':site._server.sockets[0].getsockname()[1],'chunks':chunks}),flush=True)
    try:
        await asyncio.wait_for(asyncio.to_thread(sys.stdin.readline),90)
    finally:
        step.set()
        await runner.cleanup()
        await ir.cleanup()
        print(json.dumps({'fakeRequests':calls,'externalInference':0}),flush=True)


asyncio.run(main())
