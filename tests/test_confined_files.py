"""Real bounded file tests; Windows reparse tests require no symlink privilege."""
import os
import subprocess
import pytest
from vibes.confined_files import read_bytes


def test_read_regular_relative_and_absolute(tmp_path):
    p = tmp_path / 'folder'
    p.mkdir()
    f = p / 'hello.txt'
    f.write_bytes(b'hello')
    assert read_bytes(tmp_path, 'folder/hello.txt', 5) == ('hello.txt', b'hello')
    assert read_bytes(tmp_path, str(f), 5)[1] == b'hello'


def test_size_and_traversal(tmp_path):
    (tmp_path / 'x').write_bytes(b'abcdef')
    with pytest.raises(ValueError):
        read_bytes(tmp_path, 'x', 5)
    for p in ['../x', 'a/../x', '', 'a//x']:
        with pytest.raises(ValueError):
            read_bytes(tmp_path, p, 100)


@pytest.mark.skipif(os.name != 'nt', reason='Windows path contract')
@pytest.mark.parametrize('path', ['C:relative', '//server/share/x', '\\\\?\\C:\\x', 'x:stream', 'CON', 'folder/NUL.txt', 'x.', 'x ', '/rooted'])
def test_windows_ambiguous_paths_rejected(tmp_path, path):
    with pytest.raises(ValueError):
        read_bytes(tmp_path, path, 100)


@pytest.mark.skipif(os.name != 'nt', reason='Windows junction')
def test_windows_junction_rejected(tmp_path):
    outside = tmp_path / 'outside'
    root = tmp_path / 'root'
    outside.mkdir()
    root.mkdir()
    (outside / 'private').write_text('secret')
    link = root / 'link'
    subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(outside)], check=True, capture_output=True)
    try:
        with pytest.raises(ValueError, match='reparse'):
            read_bytes(root, 'link/private', 100)
    finally:
        os.rmdir(link)


@pytest.mark.skipif(os.name != 'nt', reason='Windows handle-sharing race')
def test_ancestor_rename_and_file_write_blocked_during_read(tmp_path, monkeypatch):
    import msvcrt
    root = tmp_path / 'root'
    root.mkdir()
    folder = root / 'folder'
    folder.mkdir()
    target = folder / 'file.txt'
    target.write_bytes(b'original')
    original = msvcrt.open_osfhandle
    checked = []
    def inspect(handle, flags):
        with pytest.raises(OSError):
            folder.rename(root / 'moved')
        with pytest.raises(OSError):
            target.write_bytes(b'replacement')
        checked.append(True)
        return original(handle, flags)
    monkeypatch.setattr(msvcrt, 'open_osfhandle', inspect)
    assert read_bytes(root, 'folder/file.txt', 100)[1] == b'original'
    assert checked


@pytest.mark.skipif(os.name != 'nt', reason='Windows boot')
def test_windows_boot_with_disabled_terminal(monkeypatch):
    monkeypatch.delenv('VIBES_ENABLE_TERMINAL', raising=False)
    from vibes.app import create_app
    from vibes.routes.terminal import KEY
    app = create_app()
    assert not app[KEY].enabled
    assert app[KEY].service is None
