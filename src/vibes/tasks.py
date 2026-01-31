"""Async task queue for background processing."""

import asyncio
import logging
from typing import Callable

logger = logging.getLogger(__name__)

# Background task queue
_task_queue: asyncio.Queue | None = None
_workers: list[asyncio.Task] = []
_running = False


async def _worker(worker_id: int):
    """Worker coroutine that processes tasks from the queue."""
    global _task_queue
    logger.info(f"Task worker {worker_id} started")
    
    while _running:
        try:
            # Wait for a task with timeout to allow clean shutdown
            try:
                task_func, args, kwargs = await asyncio.wait_for(
                    _task_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            
            try:
                await task_func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Task error: {e}", exc_info=True)
            finally:
                _task_queue.task_done()
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
    
    logger.info(f"Task worker {worker_id} stopped")


async def start_task_queue(num_workers: int = 3):
    """Start the background task queue with workers."""
    global _task_queue, _workers, _running
    
    _task_queue = asyncio.Queue()
    _running = True
    
    for i in range(num_workers):
        worker = asyncio.create_task(_worker(i))
        _workers.append(worker)
    
    logger.info(f"Task queue started with {num_workers} workers")


async def stop_task_queue():
    """Stop the background task queue and all workers."""
    global _running, _workers
    
    _running = False
    
    # Wait for queue to drain (with timeout)
    if _task_queue and not _task_queue.empty():
        try:
            await asyncio.wait_for(_task_queue.join(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Task queue drain timeout, some tasks may be lost")
    
    # Cancel all workers
    for worker in _workers:
        worker.cancel()
    
    if _workers:
        await asyncio.gather(*_workers, return_exceptions=True)
    
    _workers.clear()
    logger.info("Task queue stopped")


def enqueue(task_func: Callable, *args, **kwargs):
    """Add a task to the background queue."""
    global _task_queue, _running
    
    if _task_queue is None or not _running:
        logger.warning(f"Task queue not running (queue={_task_queue}, running={_running}), task dropped")
        return False
    
    try:
        _task_queue.put_nowait((task_func, args, kwargs))
        logger.info(f"Task enqueued: {task_func.__name__}")
        return True
    except asyncio.QueueFull:
        logger.warning("Task queue full, task dropped")
        return False
