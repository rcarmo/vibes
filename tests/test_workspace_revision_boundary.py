"""Document the external-writer limitation without claiming atomic file CAS."""

import json
import os
import sys
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import make_mocked_request

from vibes.routes import workspace


@pytest.mark.asyncio
@pytest.mark.parametrize('replacement', [False, True])
async def test_external_writer_after_revision_read_is_outside_current_guarantee(tmp_path, monkeypatch, replacement):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / 'document.txt'
    target.write_text('original', encoding='utf-8')
    original_revision = workspace._file_revision(target)
    original = workspace._file_revision
    calls = 0
    environment = {name: os.environ[name] for name in ('PATH', 'SYSTEMROOT', 'WINDIR') if name in os.environ}
    environment.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path), PYTHONDONTWRITEBYTECODE='1')
    code = ("import os,sys;from pathlib import Path;p=Path(sys.argv[1]);"
            "s=Path(sys.argv[2]);s.write_text('external',encoding='utf-8');os.replace(s,p)" if replacement else
            "import sys;from pathlib import Path;Path(sys.argv[1]).write_text('external',encoding='utf-8')")
    # The external subprocess changes bytes after the validation read, before
    # the backend's comparison and separate pathname write.
    import subprocess

    def revision_with_external_race(path):
        nonlocal calls
        value = original(path)
        calls += 1
        if calls == 1:
            subprocess.run([sys.executable, '-c', code, str(target), str(tmp_path / 'replacement.txt')],
                           cwd=tmp_path, env=environment, check=True, timeout=10, capture_output=True)
            assert target.read_text(encoding='utf-8') == 'external'
        return value

    monkeypatch.setattr(workspace, '_file_revision', revision_with_external_race)
    request = make_mocked_request('PUT', '/api/workspace/file')
    request.json = AsyncMock(return_value={'path': 'document.txt', 'content': 'local draft',
                                          'expected_revision': original_revision})
    response = await workspace.classic_update_file(request)
    # This passing boundary test deliberately records the current limitation;
    # it is not acceptance of external-writer atomic compare-and-swap.
    assert response.status == 200 and target.read_text(encoding='utf-8') == 'local draft'
    assert json.loads(response.body)['revision'] == original(target)
