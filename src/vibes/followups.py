"""Shared follow-up queue state for web agent interactions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import itertools
import time
from typing import Optional


@dataclass
class FollowupItem:
    """Queued or deferred follow-up item bound to an agent thread."""

    row_id: int
    thread_id: int
    agent_id: str
    message_id: int
    content: str
    mode: str
    created_at: float
    emulated: bool = False

    def as_dict(self) -> dict:
        return {
            "row_id": self.row_id,
            "thread_id": self.thread_id,
            "agent_id": self.agent_id,
            "message_id": self.message_id,
            "content": self.content,
            "mode": self.mode,
            "created_at": self.created_at,
            "emulated": self.emulated,
        }


class _FollowupState:
    def __init__(self) -> None:
        self.row_ids = itertools.count(start=-1, step=-1)
        self.queued: list[FollowupItem] = []
        self.pending_steers: deque[FollowupItem] = deque()


_state = _FollowupState()


def reset_state() -> None:
    """Reset queue state for tests."""
    _state.row_ids = itertools.count(start=-1, step=-1)
    _state.queued = []
    _state.pending_steers = deque()


def queue_followup(
    *,
    thread_id: int,
    agent_id: str,
    message_id: int,
    content: str,
    mode: str = "queue",
    emulated: bool = False,
) -> dict:
    """Append a new queued follow-up item."""
    item = FollowupItem(
        row_id=next(_state.row_ids),
        thread_id=thread_id,
        agent_id=agent_id,
        message_id=message_id,
        content=content,
        mode=mode,
        created_at=time.time(),
        emulated=emulated,
    )
    _state.queued.append(item)
    return item.as_dict()


def defer_steer(
    *,
    thread_id: int,
    agent_id: str,
    message_id: int,
    content: str,
    emulated: bool = True,
) -> dict:
    """Append a new pending steering item that will dispatch before normal queue items."""
    item = FollowupItem(
        row_id=next(_state.row_ids),
        thread_id=thread_id,
        agent_id=agent_id,
        message_id=message_id,
        content=content,
        mode="steer",
        created_at=time.time(),
        emulated=emulated,
    )
    _state.pending_steers.append(item)
    return item.as_dict()


def promote_to_pending_steer(row_id: int, *, emulated: bool = True) -> Optional[dict]:
    """Remove a queued item and mark it as steering for the next dispatch slot."""
    for idx, item in enumerate(_state.queued):
        if item.row_id != row_id:
            continue
        promoted = _state.queued.pop(idx)
        promoted.mode = "steer"
        promoted.emulated = emulated
        _state.pending_steers.append(promoted)
        return promoted.as_dict()
    return None


def reorder_followup(row_id: int, direction: str) -> bool:
    """Move one place within its agent/thread queue, without crossing scopes."""
    if direction not in {'up', 'down'}:
        raise ValueError('direction must be up or down')
    index = next((i for i, item in enumerate(_state.queued) if item.row_id == row_id), None)
    if index is None:
        return False
    item = _state.queued[index]
    candidates = [i for i, other in enumerate(_state.queued)
                  if other.agent_id == item.agent_id and other.thread_id == item.thread_id]
    position = candidates.index(index)
    target = position + (-1 if direction == 'up' else 1)
    if 0 <= target < len(candidates):
        other = candidates[target]
        _state.queued[index], _state.queued[other] = _state.queued[other], item
    return True


def restore_followup(item: dict, *, steer: bool = False) -> dict:
    """Restore a claimed item without allocating a new public row ID."""
    restored = FollowupItem(**item)
    if steer:
        restored.mode = 'steer'
        restored.emulated = True
        _state.pending_steers.append(restored)
    else:
        _state.queued.insert(0, restored)
    return restored.as_dict()


def remove_followup(row_id: int) -> Optional[dict]:
    """Remove a queued or pending steering item."""
    for idx, item in enumerate(_state.queued):
        if item.row_id == row_id:
            removed = _state.queued.pop(idx)
            return removed.as_dict()
    for item in list(_state.pending_steers):
        if item.row_id == row_id:
            _state.pending_steers.remove(item)
            return item.as_dict()
    return None


def consume_next_followup(thread_id: int, agent_id: str) -> Optional[dict]:
    """Pop the next steering item first, otherwise FIFO queued follow-up."""
    for item in list(_state.pending_steers):
        if item.thread_id == thread_id and item.agent_id == agent_id:
            _state.pending_steers.remove(item)
            return item.as_dict()

    for idx, item in enumerate(_state.queued):
        if item.thread_id == thread_id and item.agent_id == agent_id:
            consumed = _state.queued.pop(idx)
            return consumed.as_dict()
    return None


def list_followups(*, agent_id: str | None = None, thread_id: int | None = None) -> list[dict]:
    """Return visible queued follow-up items."""
    result = []
    for item in _state.queued:
        if agent_id and item.agent_id != agent_id:
            continue
        if thread_id is not None and item.thread_id != thread_id:
            continue
        result.append(item.as_dict())
    return result


def list_pending_steers(*, agent_id: str | None = None, thread_id: int | None = None) -> list[dict]:
    """Return deferred steering items that will run before normal queue items."""
    result = []
    for item in _state.pending_steers:
        if agent_id and item.agent_id != agent_id:
            continue
        if thread_id is not None and item.thread_id != thread_id:
            continue
        result.append(item.as_dict())
    return result
