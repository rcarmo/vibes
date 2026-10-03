from vibes.native_tasks import normalise_task_event


def test_native_tasks_are_not_chats_and_errors_are_private():
    result = normalise_task_event('subagent.failed', {'toolCallId': 'task-1', 'agentDisplayName': 'Research', 'error': 'secret provider detail', 'totalTokens': 12})
    assert result == {'kind': 'native_task', 'task_id': 'task-1', 'status': 'failed', 'name': 'Research', 'total_tokens': 12}
    assert 'session_id' not in result
    assert normalise_task_event('session.idle', {'toolCallId': 'task-1'}) is None
    assert normalise_task_event('subagent.completed', {'toolCallId': ''}) is None
    assert 'duration_ms' not in normalise_task_event('subagent.started', {'toolCallId': 'x', 'duration': float('nan')})


def test_native_duration_uses_sdk_duration_ms_units():
    result = normalise_task_event('subagent.completed', {'toolCallId': 'x', 'durationMs': 1250})
    assert result['duration_ms'] == 1250


def test_native_task_identity_and_name_reject_control_characters():
    for control in ('\n', '\x00', '\x1b', '\x7f'):
        assert normalise_task_event('subagent.started', {'toolCallId': f'task{control}id'}) is None
        result = normalise_task_event('subagent.started', {'toolCallId': 'valid', 'agentDisplayName': f'name{control}'})
        assert result == {'kind': 'native_task', 'task_id': 'valid', 'status': 'running'}
