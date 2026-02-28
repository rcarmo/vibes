"""Tests for pi_client helpers: state, queue, busy, fire-and-forget."""

import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) in sys.path:
    sys.path.remove(str(SRC_PATH))
sys.path.insert(0, str(SRC_PATH))

for module_name in list(sys.modules.keys()):
    if module_name == "vibes" or module_name.startswith("vibes."):
        sys.modules.pop(module_name, None)

pi = importlib.import_module("vibes.pi_client")


@pytest.fixture(autouse=True)
def _reset():
    """Reset pi client state before each test."""
    pi.reset_state()
    yield
    pi.reset_state()


# ── is_busy ───────────────────────────────────────────────


def test_is_busy_false_when_idle():
    assert pi.is_busy() is False


@pytest.mark.asyncio
async def test_is_busy_true_when_locked():
    await pi._state.request_lock.acquire()
    try:
        assert pi.is_busy() is True
    finally:
        pi._state.request_lock.release()


# ── queue_message / pop_queued_message ────────────────────


def test_pop_queued_message_empty():
    assert pi.pop_queued_message() is None


def test_queue_and_pop_single():
    pi.queue_message("hello")
    assert pi.pop_queued_message() == "hello"
    assert pi.pop_queued_message() is None


def test_queue_fifo_order():
    pi.queue_message("first")
    pi.queue_message("second")
    pi.queue_message("third")
    assert pi.pop_queued_message() == "first"
    assert pi.pop_queued_message() == "second"
    assert pi.pop_queued_message() == "third"
    assert pi.pop_queued_message() is None


def test_reset_clears_queue():
    pi.queue_message("will be lost")
    pi.reset_state()
    assert pi.pop_queued_message() is None


# ── set_request_callback / respond_to_request ─────────────


def test_set_request_callback():
    cb = MagicMock()
    pi.set_request_callback(cb)
    assert pi._state.request_callback is cb


def test_respond_to_request_missing_id():
    assert pi.respond_to_request("nonexistent", "allow") is False


@pytest.mark.asyncio
async def test_respond_to_request_success():
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    pi._state.pending_requests["req-1"] = {"future": future}
    assert pi.respond_to_request("req-1", "allow") is True
    assert future.result() == "allow"


@pytest.mark.asyncio
async def test_respond_to_request_already_done():
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    future.set_result("deny")
    pi._state.pending_requests["req-2"] = {"future": future}
    assert pi.respond_to_request("req-2", "allow") is False


# ── cancel_current_request ────────────────────────────────


def test_cancel_no_task():
    assert pi.cancel_current_request() is False


@pytest.mark.asyncio
async def test_cancel_running_task():
    async def dummy():
        await asyncio.sleep(100)

    task = asyncio.create_task(dummy())
    pi._state.current_request_task = task
    assert pi.cancel_current_request() is True
    # Let the event loop process the cancellation
    await asyncio.sleep(0)
    assert task.cancelled()


@pytest.mark.asyncio
async def test_cancel_already_done_task():
    async def dummy():
        return 42

    task = asyncio.create_task(dummy())
    await task
    pi._state.current_request_task = task
    assert pi.cancel_current_request() is False


# ── send_rpc_fire_and_forget ──────────────────────────────


@pytest.mark.asyncio
async def test_fire_and_forget_not_running():
    result = await pi.send_rpc_fire_and_forget({"type": "steer", "message": "hi"})
    assert result is False


@pytest.mark.asyncio
async def test_fire_and_forget_success():
    with patch.object(pi, "is_pi_running", return_value=True), \
         patch.object(pi, "_send_command", new_callable=AsyncMock) as mock_send:
        result = await pi.send_rpc_fire_and_forget({"type": "steer", "message": "focus"})
        assert result is True
        mock_send.assert_called_once_with({"type": "steer", "message": "focus"})


@pytest.mark.asyncio
async def test_fire_and_forget_send_error():
    with patch.object(pi, "is_pi_running", return_value=True), \
         patch.object(pi, "_send_command", new_callable=AsyncMock, side_effect=OSError("broken pipe")):
        result = await pi.send_rpc_fire_and_forget({"type": "abort"})
        assert result is False


# ── reset_state ───────────────────────────────────────────


def test_reset_state_clears_everything():
    pi._state.rpc_buffer = "leftover data"
    pi.queue_message("msg")
    pi.set_request_callback(lambda: None)
    pi.reset_state()
    assert pi._state.rpc_buffer == ""
    assert pi._state.message_queue == []
    assert pi._state.request_callback is None
    assert pi._state.current_request_task is None
    assert pi._state.pending_requests == {}
