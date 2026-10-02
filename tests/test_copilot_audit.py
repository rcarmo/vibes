"""Deterministic second-pass regression tests. No native host or network."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from vibes import copilot_client as mod


@pytest.fixture
def host(monkeypatch):
    backend = mod.CopilotBackend()
    monkeypatch.setattr(
        mod,
        "get_config",
        lambda: SimpleNamespace(copilot_start_timeout=0.1, permission_timeout=0.1),
    )
    return backend


@pytest.mark.asyncio
async def test_cancel_during_closure_cannot_return_approval(host):
    owner = {
        "session": SimpleNamespace(session_id="s"),
        "chat_id": "c",
        "thread_id": 1,
        "turn_id": "t",
        "cancelled": False,
    }
    host.active = owner

    async def answer(payload):
        assert host.respond(payload["request_id"], "allow")

    async def close(payload):
        owner["cancelled"] = True

    host.request_callback = answer
    host.request_closed_callback = close
    decision = await host._permission({"kind": "read"}, {"session_id": "s"})
    assert decision.to_dict()["kind"] != "approved"
    from copilot.generated.rpc import PermissionDecisionReject

    assert isinstance(decision, PermissionDecisionReject)


@pytest.mark.asyncio
async def test_cancel_during_closure_cannot_return_answer(host):
    owner = {
        "session": SimpleNamespace(session_id="s"),
        "chat_id": "c",
        "thread_id": 1,
        "turn_id": "t",
        "cancelled": False,
    }
    host.active = owner

    async def answer(payload):
        assert host.respond(payload["request_id"], "choice-0")

    async def close(payload):
        host.active = {**owner, "turn_id": "new"}

    host.request_callback = answer
    host.request_closed_callback = close
    with pytest.raises(PermissionError):
        await host._question(
            {"question": "Pick", "choices": ["One"]}, {"session_id": "s"}
        )


@pytest.mark.asyncio
async def test_shutdown_does_not_hold_start_lock_while_draining(host):
    host.client = SimpleNamespace(stop=AsyncMock())
    client = host.client
    async with host.turn_lock:
        stopping = asyncio.create_task(host.stop(permanent=True))
        await asyncio.sleep(0)
        assert host.closing
        # Previous lock inversion caused a six-second timeout and poisoned host.
        with pytest.raises(RuntimeError, match="shutting down"):
            await asyncio.wait_for(host.start(), 0.1)
    await asyncio.wait_for(stopping, 0.2)
    client.stop.assert_awaited_once()
    assert host.closing and not host.poisoned


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["model", "models"])
async def test_controls_setup_timeout_poisoned_not_recreated(host, method):
    host.start = AsyncMock()

    async def slow(*args):
        await asyncio.Event().wait()

    host._session = AsyncMock(side_effect=slow)
    with pytest.raises(RuntimeError, match="session setup failed"):
        await getattr(host, method)("chat", SimpleNamespace())
    assert host.poisoned and not host.turn_lock.locked()


def test_catalog_only_exposes_bounded_metadata():
    rows = mod._model_rows(
        [
            {
                "id": "safe",
                "name": {"token": "private"},
                "supportedReasoningEfforts": "high",
                "endpoint": "private",
            },
            {"id": "safe", "name": "duplicate"},
            {"id": []},
            {"id": "x" * 513},
            {
                "id": "reasoner",
                "supportedReasoningEfforts": ["low", {}, "high", "low", "bad\nvalue"],
            },
        ]
    )
    assert rows == [
        {
            "id": "safe",
            "provider": "copilot",
            "name": "safe",
            "reasoning": False,
            "efforts": [],
        },
        {
            "id": "reasoner",
            "provider": "copilot",
            "name": "reasoner",
            "reasoning": True,
            "efforts": ["low", "high"],
        },
    ]
    assert mod._model_rows({"private": "config"}) == []


@pytest.mark.asyncio
async def test_request_callback_is_part_of_permission_deadline(host):
    host.active = {"chat_id": "c", "thread_id": 1, "turn_id": "t", "cancelled": False}

    async def blocked(payload):
        await asyncio.Event().wait()

    host.request_callback = blocked
    assert (
        await asyncio.wait_for(host._decision("test", {}, [{"optionId": "allow"}]), 0.2)
        == "deny"
    )
    assert not host.pending
