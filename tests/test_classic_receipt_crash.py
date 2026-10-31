"""Independent processes cannot replay a prompt after abrupt admission exit."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest


CHILD = r'''
import asyncio,json,os,sys
from pathlib import Path
from unittest.mock import AsyncMock
from aiohttp.test_utils import make_mocked_request
# Config imports python-dotenv; disable discovery before importing Vibes.
import dotenv
dotenv.load_dotenv=lambda *args,**kwargs:False
from vibes.db import Database
from vibes.routes import classic,agents
path,stage,operation=sys.argv[1:]
async def main():
 db=Database(path);await db.connect()
 classic.get_db=agents.get_db=AsyncMock(return_value=db)
 agents._resolve_agent_mode=lambda _: 'pi'
 agents._is_agent_busy=lambda _:False
 agents.broadcast_event=AsyncMock()
 agents.queue_link_preview_fetch=lambda *args:None
 marker=Path(path+'.dispatch')
 def enqueue(*args,**kwargs):
  if operation=='recover':raise AssertionError('redispatch after process crash')
  with marker.open('ab') as stream:
   stream.write(b'admitted\n');stream.flush();os.fsync(stream.fileno())
  if stage=='enqueue':os._exit(73)
  return True
 agents.enqueue=enqueue
 if operation=='crash':
  if stage=='claim':
   original=classic._claim
   async def claim(*args):
    await original(*args);os._exit(71)
   classic._claim=claim
  elif stage=='message':
   async def after_message(*args):os._exit(72)
   agents.broadcast_event=after_message
  elif stage=='finalize':
   original=classic._finalize
   async def finalize(*args):
    await original(*args);os._exit(74)
   classic._finalize=finalize
 request=make_mocked_request('POST','/api/sessions/default/prompt',match_info={'id':'default'})
 request.json=AsyncMock(return_value={'prompt':'crash once','client_request_id':'crash'})
 response=await classic.prompt(request)
 row=await classic._receipt(db,'default','crash')
 posts=await db.get_timeline()
 print(json.dumps({'status':response.status,'result':json.loads(response.body),'receipt':row['state'],
                   'posts':len(posts),'marker':marker.read_text().count('admitted') if marker.exists() else 0}))
 await db.close()
asyncio.run(main())
'''


@pytest.mark.asyncio
@pytest.mark.parametrize('stage,exit_code,posts,dispatches', [
    ('claim', 71, 0, 0), ('message', 72, 1, 0), ('enqueue', 73, 1, 1), ('finalize', 74, 1, 1),
])
async def test_abrupt_exit_no_replay_in_new_process(tmp_path, stage, exit_code, posts, dispatches):
    path = str(tmp_path / 'crash.db')
    # Only inherit the test/tool path configuration, never provider credentials.
    allowed = ('PATH', 'PYTHONPATH', 'PYTHONPYCACHEPREFIX', 'TMPDIR', 'TMP', 'TEMP', 'SYSTEMROOT', 'WINDIR')
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    if 'PYTHONPATH' in environment:
        environment['PYTHONPATH'] = os.pathsep.join(str(Path(value or '.').resolve()) for value in environment['PYTHONPATH'].split(os.pathsep))
    environment.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYTHONDONTWRITEBYTECODE='1')

    async def child(operation):
        process = await asyncio.create_subprocess_exec(sys.executable, '-c', CHILD, path, stage, operation,
                                                       env=environment, cwd=tmp_path, stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE)
        try:
            output, error = await asyncio.wait_for(process.communicate(), 15)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        return process.returncode, output.decode(), error.decode()

    code, _, error = await child('crash')
    assert code == exit_code, error
    code, output, error = await child('recover')
    assert code == 0, error
    data = json.loads(output)
    assert data['posts'] == posts and data['marker'] == dispatches
    assert data['receipt'] == ('confirmed' if stage == 'finalize' else 'pending')
    assert data['status'] == (201 if stage == 'finalize' else 409)
    if stage != 'finalize':
        assert data['result']['code'] == 'admission_uncertain'
