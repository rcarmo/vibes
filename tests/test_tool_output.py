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
