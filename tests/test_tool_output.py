from vibes.tool_output import ToolOutputState


def test_call_output_is_bounded_and_timer_survives_completion():
    state = ToolOutputState(limit=5)
    started = state.update({'type': 'tool_call', 'tool_call_id': 'a'})
    output = state.update({'type': 'tool_output', 'tool_call_id': 'a', 'content': '1234567'})
    assert output['output'] == '34567'
    assert output['output_truncated'] is True
    complete = state.update({'type': 'tool_status', 'tool_call_id': 'a', 'status': 'failed'})
    assert complete['started_at'] == started['started_at']
    assert complete['output'] == '34567'
    assert complete['status'] == 'failed'
    other = state.update({'type': 'tool_call', 'tool_call_id': 'b'})
    assert other['output'] == ''


def test_interleaved_tools_keep_output_and_progress_separate():
    state = ToolOutputState(limit=8)
    state.update({'type': 'tool_call', 'tool_call_id': 'a'})
    state.update({'type': 'tool_call', 'tool_call_id': 'b'})
    state.update({'type': 'tool_output', 'tool_call_id': 'a', 'content': 'alpha'})
    state.update({'type': 'tool_output', 'tool_call_id': 'b', 'content': 'beta'})
    progress = state.update({'type': 'tool_output', 'tool_call_id': 'a', 'content': 'working', 'progress': True})
    assert progress['output'] == 'alpha'
    assert progress['progress_message'] == 'working'
    complete = state.update({'type': 'tool_status', 'tool_call_id': 'a', 'status': 'completed'})
    assert complete['ended_at'] >= complete['started_at']
    repeated = state.update({'type': 'tool_status', 'tool_call_id': 'a', 'status': 'completed'})
    assert repeated['ended_at'] == complete['ended_at']
    other = state.update({'type': 'tool_status', 'tool_call_id': 'b', 'status': 'failed'})
    assert other['output'] == 'beta'
    assert 'progress_message' not in other


def test_reconnect_snapshot_retains_multiple_calls_with_aggregate_bound():
    state = ToolOutputState(limit=16000)
    for i in range(6):
        state.update({'type': 'tool_call', 'tool_call_id': str(i), 'title': f'tool-{i}', 'status': 'running'})
        state.update({'type': 'tool_output', 'tool_call_id': str(i), 'content': 'x' * 16000})
        state.update({'type': 'tool_status', 'tool_call_id': str(i), 'status': 'completed'})
    snapshot = state.update({'type': 'writing', 'title': 'Writing response'})['tool_calls']
    assert len(snapshot) == 6
    assert sum(len(row['output']) for row in snapshot) <= 64000
    assert all(row['status'] == 'completed' for row in snapshot)
    assert snapshot[0]['output_truncated'] is True
    assert snapshot[-1]['title'] == 'tool-5'


def test_reconnect_budget_includes_progress_messages():
    state = ToolOutputState(limit=16000)
    for i in range(8):
        state.update({'type': 'tool_output', 'tool_call_id': str(i), 'content': 'p' * 16000, 'progress': True})
    rows = state.snapshot()
    assert sum(len(row['output']) + len(row['progress_message']) for row in rows) <= 64000
    assert any(row['progress_truncated'] for row in rows)


def test_call_count_limit_retains_snapshot_and_reports_omission():
    state = ToolOutputState(limit=1)
    for i in range(256):
        state.update({'type': 'tool_call', 'tool_call_id': str(i)})
    result = state.update({'type': 'tool_call', 'tool_call_id': 'overflow'})
    assert len(result['tool_calls']) == 256
    assert result['tool_calls_truncated'] is True
    assert 'overflow' not in state.calls


def test_progress_source_truncation_survives_reconnect():
    state = ToolOutputState(limit=5)
    state.update({'type': 'tool_output', 'tool_call_id': 'a', 'content': 'short',
                  'progress': True, 'content_truncated': True})
    assert state.snapshot()[0]['progress_truncated'] is True
    state.update({'type': 'tool_output', 'tool_call_id': 'a', 'content': 'complete', 'progress': True})
    assert state.snapshot()[0]['progress_truncated'] is True
    state.update({'type': 'tool_output', 'tool_call_id': 'a', 'content': 'done', 'progress': True})
    assert state.snapshot()[0]['progress_truncated'] is False


def test_call_omission_marker_survives_retained_call_and_phase_updates():
    state = ToolOutputState()
    for i in range(257):
        state.update({'type': 'tool_call', 'tool_call_id': str(i)})
    assert state.update({'type': 'tool_status', 'tool_call_id': '0', 'status': 'completed'})['tool_calls_truncated']
    assert state.update({'type': 'writing'})['tool_calls_truncated']


def test_final_output_replaces_partial_text_without_duplication():
    state = ToolOutputState(limit=5)
    state.update({'type': 'tool_output', 'tool_call_id': 'a', 'content': 'abc'})
    result = state.update({'type': 'tool_output', 'tool_call_id': 'a', 'content': 'abcde', 'replace_output': True})
    assert result['output'] == 'abcde'
    assert result['output_truncated'] is False
