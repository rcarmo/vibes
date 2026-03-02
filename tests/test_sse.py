"""Tests for SSE broadcast and client management."""

import asyncio
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) in sys.path:
    sys.path.remove(str(SRC_PATH))
sys.path.insert(0, str(SRC_PATH))

for module_name in list(sys.modules.keys()):
    if module_name == "vibes" or module_name.startswith("vibes."):
        sys.modules.pop(module_name, None)

sse = importlib.import_module("vibes.routes.sse")


@pytest.fixture(autouse=True)
def _cleanup():
    """Clear SSE client set after each test."""
    sse._clients.clear()
    sse._restart_task = None
    yield
    sse._clients.clear()
    sse._restart_task = None


# ── broadcast_event ───────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_no_clients():
    # Should not error
    await sse.broadcast_event("test", {"key": "value"})


@pytest.mark.asyncio
async def test_broadcast_single_client():
    queue = asyncio.Queue(maxsize=100)
    sse._clients.add(queue)
    await sse.broadcast_event("new_post", {"id": 1})
    msg = queue.get_nowait()
    assert "event: new_post" in msg
    assert '"id": 1' in msg


@pytest.mark.asyncio
async def test_broadcast_multiple_clients():
    q1 = asyncio.Queue(maxsize=100)
    q2 = asyncio.Queue(maxsize=100)
    sse._clients.add(q1)
    sse._clients.add(q2)
    await sse.broadcast_event("agent_response", {"text": "hello"})
    assert q1.qsize() == 1
    assert q2.qsize() == 1


@pytest.mark.asyncio
async def test_broadcast_lossy_event_dropped_when_full():
    queue = asyncio.Queue(maxsize=2)
    sse._clients.add(queue)
    # Fill queue
    queue.put_nowait("filler1")
    queue.put_nowait("filler2")
    # Lossy event should be silently dropped
    await sse.broadcast_event("agent_status", {"type": "thinking"})
    assert queue.qsize() == 2


@pytest.mark.asyncio
async def test_broadcast_lossy_draft_dropped_when_full():
    queue = asyncio.Queue(maxsize=1)
    sse._clients.add(queue)
    queue.put_nowait("filler")
    await sse.broadcast_event("agent_draft", {"text": "draft"})
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_broadcast_lossy_thought_dropped_when_full():
    queue = asyncio.Queue(maxsize=1)
    sse._clients.add(queue)
    queue.put_nowait("filler")
    await sse.broadcast_event("agent_thought", {"text": "hmm"})
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_broadcast_lossy_thought_delta_dropped_when_full():
    queue = asyncio.Queue(maxsize=1)
    sse._clients.add(queue)
    queue.put_nowait("filler")
    await sse.broadcast_event("agent_thought_delta", {"delta": "h"})
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_broadcast_critical_event_evicts_stale():
    queue = asyncio.Queue(maxsize=2)
    sse._clients.add(queue)
    queue.put_nowait("old1")
    queue.put_nowait("old2")
    # Critical event should evict stale messages to make room
    await sse.broadcast_event("agent_response", {"id": 42})
    # Drain and check that the new event is present
    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    assert any("agent_response" in m for m in messages)


@pytest.mark.asyncio
async def test_broadcast_message_format():
    queue = asyncio.Queue(maxsize=100)
    sse._clients.add(queue)
    await sse.broadcast_event("my_event", {"foo": "bar"})
    msg = queue.get_nowait()
    assert msg.startswith("event: my_event\n")
    assert "data: " in msg
    data_line = msg.split("data: ")[1].split("\n")[0]
    parsed = json.loads(data_line)
    assert parsed == {"foo": "bar"}


# ── _schedule_restart_if_needed ───────────────────────────


@pytest.mark.asyncio
async def test_schedule_restart_noop_with_clients():
    queue = asyncio.Queue(maxsize=100)
    sse._clients.add(queue)
    sse._schedule_restart_if_needed()
    assert sse._restart_task is None


@pytest.mark.asyncio
async def test_schedule_restart_cancels_when_client_connects():
    # Simulate a restart being scheduled
    async def dummy():
        await asyncio.sleep(100)
    sse._restart_task = asyncio.create_task(dummy())
    # A client connects
    queue = asyncio.Queue(maxsize=100)
    sse._clients.add(queue)
    sse._schedule_restart_if_needed()
    assert sse._restart_task is None


@pytest.mark.asyncio
async def test_schedule_restart_noop_with_zero_timeout():
    with patch.object(sse, "get_config") as mock_config:
        mock_config.return_value.disconnect_timeout = 0
        sse._schedule_restart_if_needed()
        assert sse._restart_task is None


# ── lossy event types ─────────────────────────────────────


def test_lossy_event_types():
    assert "agent_status" in sse._LOSSY_EVENT_TYPES
    assert "agent_draft" in sse._LOSSY_EVENT_TYPES
    assert "agent_thought" in sse._LOSSY_EVENT_TYPES
    assert "agent_thought_delta" in sse._LOSSY_EVENT_TYPES
    assert "new_post" not in sse._LOSSY_EVENT_TYPES
    assert "agent_response" not in sse._LOSSY_EVENT_TYPES
