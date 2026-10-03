from types import SimpleNamespace
from vibes.diagnostics import backend_diagnostics


def test_diagnostics_never_exports_mcp_secrets_or_execution_claims():
    config = SimpleNamespace(default_agent='copilot-ffi', copilot_skill_directories=['notes/skills'], copilot_available_tools=['safe'], copilot_mcp_servers={'server': {'env': {'TOKEN': 'private-secret'}, 'args': ['private-arg']}}, memory_paths=['note.md'], memory_diagnostics=[{'path': 'missing.md', 'status': 'missing'}])
    result = backend_diagnostics(config)
    assert result['execution_verified'] is False
    assert result['mcp'] == [{'name': 'server', 'state': 'configured'}]
    assert 'private-secret' not in repr(result) and 'private-arg' not in repr(result)
    assert result['memory']['sources'] == ['note.md']


def test_diagnostic_labels_are_bounded_and_display_safe():
    unsafe = ['safe', 'bad\nlabel', 'x' * 513, True, '  ', 'del\x7f']
    config = SimpleNamespace(default_agent='copilot-ffi', copilot_skill_directories=unsafe,
                             copilot_available_tools=unsafe, copilot_mcp_servers={'safe': {}, 'bad\nname': {}},
                             memory_paths=unsafe, memory_diagnostics=[])
    result = backend_diagnostics(config)
    assert result['skills'] == [{'source': 'safe', 'state': 'configured'}]
    assert result['tools'] == [{'name': 'safe', 'state': 'configured'}]
    assert result['mcp'] == [{'name': 'safe', 'state': 'configured'}]
    assert result['memory']['sources'] == ['safe']


def test_memory_diagnostics_export_only_safe_known_fields():
    config = SimpleNamespace(default_agent='pi', memory_diagnostics=[
        {'path': 'notes/missing.md', 'status': 'missing', 'secret': 'do-not-export'},
        {'path': 'notes/large.md', 'status': 'over-budget'},
        {'path': 'notes/binary.md', 'status': 'invalid-utf8'},
        {'path': 'bad\npath.md', 'status': 'missing'},
        {'path': 'x' * 513, 'status': 'missing'},
        {'path': True, 'status': 'missing'},
        {'path': 'safe.md', 'status': ['missing']},
        {'path': 'safe.md', 'status': 'private runtime error'},
        'private',
    ])
    result = backend_diagnostics(config)
    assert result['memory']['diagnostics'] == [
        {'path': 'notes/missing.md', 'status': 'missing'},
        {'path': 'notes/large.md', 'status': 'over-budget'},
        {'path': 'notes/binary.md', 'status': 'invalid-utf8'},
    ]
    assert 'do-not-export' not in str(result)
    config.memory_diagnostics = [{'path': 'safe.md', 'status': 'missing'}] * 20
    assert len(backend_diagnostics(config)['memory']['diagnostics']) == 16


def test_diagnostics_http_is_read_only_and_not_cacheable():
    import asyncio
    import json
    from unittest.mock import MagicMock, patch
    from vibes import app

    config = SimpleNamespace(
        default_agent='copilot-ffi',
        copilot_skill_directories=['skills'],
        copilot_available_tools=['read'],
        copilot_mcp_servers={'local': {'env': {'TOKEN': 'private-token'}, 'args': ['private-argument']}},
        memory_paths=['notes.md'],
        memory_diagnostics=[{'path': 'notes.md', 'status': 'missing', 'error': 'private-error'}],
    )
    backend = MagicMock()
    with patch.object(app, 'get_config', return_value=config), \
         patch('vibes.copilot_host.backend', backend):
        response = asyncio.run(app.diagnostics_handler(MagicMock()))
    assert response.status == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.content_type == 'application/json'
    payload = json.loads(response.text)
    assert payload['execution_verified'] is False
    assert payload['tools'] == [{'name': 'read', 'state': 'configured'}]
    assert payload['memory']['diagnostics'] == [{'path': 'notes.md', 'status': 'missing'}]
    assert 'private-' not in response.text
    assert backend.mock_calls == []
