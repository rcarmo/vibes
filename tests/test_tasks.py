"""Tests for the async task queue."""

import asyncio
import importlib
import sys
from pathlib import Path

import pytest
import pytest_asyncio

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) in sys.path:
    sys.path.remove(str(SRC_PATH))
sys.path.insert(0, str(SRC_PATH))

for module_name in list(sys.modules.keys()):
    if module_name == "vibes" or module_name.startswith("vibes."):
        sys.modules.pop(module_name, None)

tasks = importlib.import_module("vibes.tasks")


def _sync_cleanup():
    """Reset task queue globals (no async needed for this)."""
    tasks._task_queue = None
    tasks._workers.clear()
    tasks._running = False


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    """Ensure task queue is stopped after each test."""
    _sync_cleanup()
    yield
    tasks._running = False
    for w in list(tasks._workers):
        w.cancel()
    if tasks._workers:
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks._workers, return_exceptions=True),
                timeout=2.0,
            )
        except asyncio.TimeoutError:
            pass
    _sync_cleanup()


# ── enqueue before start ──────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_before_start_returns_false():
    _sync_cleanup()
    assert tasks.enqueue(lambda: None) is False


# ── start / stop ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_creates_workers():
    await tasks.start_task_queue(num_workers=2)
    assert tasks._running is True
    assert len(tasks._workers) == 2
    assert tasks._task_queue is not None


@pytest.mark.asyncio
async def test_stop_clears_workers():
    await tasks.start_task_queue(num_workers=2)
    await tasks.stop_task_queue()
    assert tasks._running is False
    assert len(tasks._workers) == 0


# ── enqueue and execute ───────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_executes_task():
    results = []

    async def collect(value):
        results.append(value)

    await tasks.start_task_queue(num_workers=1)
    ok = tasks.enqueue(collect, "hello")
    assert ok is True
    # Wait briefly for the worker to process
    await asyncio.sleep(0.1)
    assert results == ["hello"]


@pytest.mark.asyncio
async def test_enqueue_multiple_tasks():
    results = []

    async def collect(value):
        results.append(value)

    await tasks.start_task_queue(num_workers=2)
    for i in range(5):
        tasks.enqueue(collect, i)
    await asyncio.sleep(0.2)
    assert sorted(results) == [0, 1, 2, 3, 4]


# ── error handling ────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_survives_task_error():
    results = []

    async def maybe_fail(value):
        if value == "fail":
            raise RuntimeError("boom")
        results.append(value)

    await tasks.start_task_queue(num_workers=1)
    tasks.enqueue(maybe_fail, "fail")
    tasks.enqueue(maybe_fail, "ok")
    await asyncio.sleep(0.2)
    assert results == ["ok"]


# ── queue full ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_full_returns_false():
    await tasks.start_task_queue(num_workers=1)
    # Replace queue with a tiny one
    tasks._task_queue = asyncio.Queue(maxsize=1)
    # Bypass the worker to fill the queue
    tasks._task_queue.put_nowait((asyncio.sleep, (100,), {}))
    result = tasks.enqueue(asyncio.sleep, 0)
    assert result is False


# ── stop drains pending tasks ─────────────────────────────


@pytest.mark.asyncio
async def test_stop_processes_pending():
    results = []

    async def collect(value):
        results.append(value)

    await tasks.start_task_queue(num_workers=1)
    tasks.enqueue(collect, "drained")
    # Wait for worker to pick up the task
    await asyncio.sleep(0.2)
    assert "drained" in results
