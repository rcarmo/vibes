import pytest
from vibes.workspace_memory import load_workspace_memory


def test_memory_is_explicit_bounded_and_read_only(tmp_path):
    (tmp_path / 'note.md').write_text('operator note', encoding='utf-8')
    (tmp_path / 'large.md').write_text('x' * 100)
    result = load_workspace_memory(tmp_path, ['note.md', 'missing.md', 'large.md'], max_bytes=30)
    assert result['sources'][0]['path'] == 'note.md'
    assert result['bytes'] == len(b'operator note')
    assert result['diagnostics'] == [{'path': 'missing.md', 'status': 'missing'}, {'path': 'large.md', 'status': 'over-budget'}]
    assert (tmp_path / 'note.md').read_text() == 'operator note'
    for paths in [['../outside.md'], ['/etc/secrets.md'], ['note.txt']]:
        with pytest.raises(ValueError):
            load_workspace_memory(tmp_path, paths)


def test_memory_does_not_follow_outside_symlinks(tmp_path):
    outside = tmp_path.parent / 'outside-memory.md'
    outside.write_text('private')
    (tmp_path / 'link.md').symlink_to(outside)
    with pytest.raises(ValueError):
        load_workspace_memory(tmp_path, ['link.md'])
