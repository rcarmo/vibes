"""Independent-process compaction exits never authorise native redispatch."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest


CHILD = r'''
import asyncio,json,os,sys
from pathlib import Path
from types import SimpleNamespace
import dotenv
dotenv.load_dotenv=lambda *args,**kwargs:False
from vibes.compaction import Compactions
from vibes.copilot_host import CopilotHost
from vibes.db import Database
from vibes.routes import agents
path,stage,operation=sys.argv[1:]
async def main():
 db=Database(path);await db.connect()
 manager=Compactions();host=CopilotHost()
 marker=Path(path+'.native')
 if operation=='recover':
  await manager.recover(db)
  token=Path(path+'.token').read_text()
  result=await manager.admit(db,host,'default',token)
  assert not host.lanes and not manager.tasks
  print(json.dumps({'operation':result,'native_attempts':marker.read_text().count('attempt') if marker.exists() else 0,
                    'blocked':await db.compaction_blocked('default')}))
  await db.close();return
 host.client=object();lane=host.lane('default');lane.client=host.client
 async def compact(**kwargs):
  with marker.open('ab') as stream:
   stream.write(b'attempt\n');stream.flush();os.fsync(stream.fileno())
  if stage=='native':os._exit(82)
  return {'success':True,'messagesRemoved':1,'tokensRemoved':5}
 lane.sessions['default']=SimpleNamespace(rpc=SimpleNamespace(history=SimpleNamespace(
  compact=compact,abort_manual_compaction=lambda **kw:None)))
 capability=await manager.capability(db,host,'default');assert capability['available']
 token=capability['token'];Path(path+'.token').write_text(token)
 if stage=='admission':
  original=db._connection.commit
  async def commit():
   await original();os._exit(81)
  db._connection.commit=commit
 elif stage=='completion':
  original=manager._state
  async def state(*args,**kwargs):
   await original(*args,**kwargs)
   if args[2]=='completed':os._exit(83)
  manager._state=state
 await manager.admit(db,host,'default',token)
 await asyncio.gather(*list(manager.tasks.values()))
 raise AssertionError('crash seam did not terminate')
asyncio.run(main())
'''


@pytest.mark.asyncio
@pytest.mark.parametrize('stage,exit_code,attempts,expected', [
    ('admission', 81, 0, 'uncertain'), ('native', 82, 1, 'uncertain'),
    ('completion', 83, 1, 'completed'),
])
async def test_compaction_process_exit_no_native_replay(tmp_path, stage, exit_code, attempts, expected):
    path = str(tmp_path / 'compaction.db')
    allowed = ('PATH', 'PYTHONPATH', 'PYTHONPYCACHEPREFIX', 'TMPDIR', 'TMP', 'TEMP', 'SYSTEMROOT', 'WINDIR')
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    if 'PYTHONPATH' in environment:
        environment['PYTHONPATH'] = os.pathsep.join(str(Path(value or '.').resolve()) for value in environment['PYTHONPATH'].split(os.pathsep))
    environment.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYTHONDONTWRITEBYTECODE='1')

    async def child(operation):
        process = await asyncio.create_subprocess_exec(sys.executable, '-c', CHILD, path, stage, operation,
                                                       env=environment, cwd=tmp_path,
                                                       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
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
    result = json.loads(output)
    assert result['operation']['state'] == expected and result['operation']['recovered']
    assert result['native_attempts'] == attempts
    assert result['blocked'] == (expected == 'uncertain')
