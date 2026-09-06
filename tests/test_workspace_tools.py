import importlib
import os
import pytest

WorkspaceTools = importlib.import_module('vibes.workspace_tools').WorkspaceTools


def test_bounded_reads_and_rejected_paths(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'file.txt').write_text('abcdefgh')
    tools = WorkspaceTools(root)
    assert tools.read('file.txt', 2, 3)['text'] == 'cde'
    assert tools.read('file.txt', 2, 3)['has_more']
    (tmp_path / 'secret').write_text('secret')
    (root / 'link').symlink_to(tmp_path / 'secret')
    (root / 'dirlink').symlink_to(tmp_path, target_is_directory=True)
    for path in ['../secret', '/etc/passwd', 'link', 'dirlink/secret', './file.txt']:
        with pytest.raises((ValueError, OSError)):
            tools.read(path)
    os.mkfifo(root / 'pipe')
    with pytest.raises(ValueError):
        tools.read('pipe')
    (root / 'binary').write_bytes(b'a\0b')
    with pytest.raises(ValueError):
        tools.read('binary')
