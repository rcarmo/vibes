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


def test_directory_listing_is_bounded_and_does_not_follow_symlinks(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'folder').mkdir()
    (root / 'file').write_text('text')
    (root / 'link').symlink_to(tmp_path, target_is_directory=True)
    tools = WorkspaceTools(root)
    result = tools.list_directory()
    assert {x['name']: x['type'] for x in result['entries']} == {'folder': 'directory', 'file': 'file', 'link': 'symlink'}
    assert not result['truncated']
    assert len(tools.list_directory(limit=1)['entries']) == 1
    assert tools.list_directory(limit=1)['truncated']
    for path in ['link', '../', '/tmp']:
        with pytest.raises((ValueError, OSError)):
            tools.list_directory(path)
