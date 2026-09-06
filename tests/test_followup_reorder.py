import importlib
import pytest

queue = importlib.import_module('vibes.followups')


def test_reorder_preserves_scope_and_steer_priority():
    queue.reset_state()
    try:
        a = queue.queue_followup(thread_id=1, agent_id='a', message_id=1, content='first')
        other = queue.queue_followup(thread_id=2, agent_id='b', message_id=2, content='other')
        b = queue.queue_followup(thread_id=1, agent_id='a', message_id=3, content='second')
        steer = queue.defer_steer(thread_id=1, agent_id='a', message_id=4, content='urgent')
        assert queue.reorder_followup(b['row_id'], 'up')
        assert [x['row_id'] for x in queue.list_followups()] == [b['row_id'], other['row_id'], a['row_id']]
        assert queue.consume_next_followup(thread_id=1, agent_id='a')['row_id'] == steer['row_id']
        assert queue.consume_next_followup(thread_id=1, agent_id='a')['row_id'] == b['row_id']
        assert not queue.reorder_followup(-9999, 'up')
        with pytest.raises(ValueError):
            queue.reorder_followup(a['row_id'], 'sideways')
    finally:
        queue.reset_state()
