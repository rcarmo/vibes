from types import SimpleNamespace
from vibes.diagnostics import backend_diagnostics


def test_diagnostics_never_exports_mcp_secrets_or_execution_claims():
    config = SimpleNamespace(default_agent='copilot-ffi', copilot_skill_directories=['notes/skills'], copilot_available_tools=['safe'], copilot_mcp_servers={'server': {'env': {'TOKEN': 'private-secret'}, 'args': ['private-arg']}}, memory_paths=['note.md'], memory_diagnostics=[{'path': 'missing.md', 'status': 'missing'}])
    result = backend_diagnostics(config)
    assert result['execution_verified'] is False
    assert result['mcp'] == [{'name': 'server', 'state': 'configured'}]
    assert 'private-secret' not in repr(result) and 'private-arg' not in repr(result)
    assert result['memory']['sources'] == ['note.md']
