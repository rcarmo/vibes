"""Concurrent chat lanes, routing and transaction isolation; no native/model calls."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import web
from vibes import copilot_client as mod
from vibes.copilot_host import CopilotHost
from vibes.sessions import SessionStore


class HeldSession:
    def __init__(self, sid):
        self.session_id = sid
        self.handler = None
        self.entered = asyncio.Event()
        self.prompts = []
        self.abort_count = 0

    def on(self, handler):
        self.handler = handler
        return lambda: setattr(self, "handler", None)

    async def send(self, content, **kwargs):
        self.prompts.append(content)
        self.entered.set()

    def event(self, kind, data):
        self.handler(SimpleNamespace(type=kind, data=data))

    def finish(self, text):
        self.event("assistant.message_delta", {"deltaContent": text})
        self.event("assistant.message", {"content": text})
        self.event("session.idle", {})

    async def abort(self):
        self.abort_count += 1
        if self.handler:
            self.event("session.idle", {})


@pytest.fixture
def host(monkeypatch, tmp_path):
    created = []

    async def create(**kwargs):
        session = HeldSession(kwargs["session_id"])
        created.append(session)
        return session

    client = SimpleNamespace(
        start=AsyncMock(),
        stop=AsyncMock(),
        get_status=AsyncMock(return_value={"version": mod.RUNTIME_VERSION}),
        create_session=AsyncMock(side_effect=create),
        rpc=SimpleNamespace(sessions=SimpleNamespace(save=AsyncMock())),
    )
    sdk = SimpleNamespace(
        CopilotClient=Mock(return_value=client),
        RuntimeConnection=SimpleNamespace(for_inprocess=lambda: "ffi"),
        RemoteSessionMode=SimpleNamespace(OFF="off"),
        Tool=lambda **kwargs: SimpleNamespace(**kwargs),
        ToolResult=lambda **kwargs: kwargs,
    )
    config = SimpleNamespace(
        copilot_state_dir=str(tmp_path / "native"),
        copilot_model=None,
        copilot_use_logged_in_user=False,
        copilot_start_timeout=1,
        copilot_event_timeout=5,
        permission_timeout=10,
        copilot_available_tools=[],
        copilot_skill_directories=[],
    )
    monkeypatch.setattr(mod, "_sdk", lambda: sdk)
    monkeypatch.setattr(mod, "get_config", lambda: config)
    return CopilotHost(), client, created


def context(chat):
    return {
        "mode": "copilot-ffi",
        "session_id": chat,
        "turn_id": "turn-" + chat,
        "thread_id": 1,
        "agent_id": "default",
        "receipts": {},
    }


@pytest.mark.asyncio
async def test_six_sessions_overlap_cancel_and_permissions_are_isolated(host):
    backend, client, created = host
    store = SimpleNamespace(
        backend_binding=AsyncMock(return_value=None), bind_backend=AsyncMock()
    )
    backend.request_callback = AsyncMock()
    tasks = [
        asyncio.create_task(
            backend.send(
                str(i),
                1,
                AsyncMock(),
                chat_id=str(i),
                store=store,
                attachment_context=context(str(i)),
            )
        )
        for i in range(6)
    ]
    async with asyncio.timeout(3):
        while len(created) < 6 or not all(s.entered.is_set() for s in created):
            await asyncio.sleep(0.001)
    assert backend.status()["active_chats"] == 6
    client.start.assert_awaited_once()
    decisions = [
        asyncio.create_task(
            backend.lane(str(i))._decision(
                "test", {}, [{"optionId": "allow"}, {"optionId": "deny"}]
            )
        )
        for i in range(6)
    ]
    async with asyncio.timeout(2):
        while len(backend.pending_requests()) < 6:
            await asyncio.sleep(0.001)
    for i in range(6):
        assert len(backend.pending_requests(str(i))) == 1
    first = backend.pending_requests("0")[0]["request_id"]
    assert not await backend.abort("1", backend.active_for("0"))
    assert await backend.abort("0", backend.active_for("0"))
    assert not backend.respond(first, "allow")
    assert await decisions[0] == "deny"
    assert (await tasks[0])["cancelled"]
    for i in range(1, 6):
        assert backend.busy(str(i))
        assert backend.respond(
            backend.pending_requests(str(i))[0]["request_id"], "allow"
        )
        assert await decisions[i] == "allow"
        backend.active_for(str(i))["session"].finish("reply-" + str(i))
    replies = await asyncio.gather(*tasks[1:])
    assert [r["text"] for r in replies] == ["reply-" + str(i) for i in range(1, 6)]
    assert not backend.busy() and not backend.pending_requests()
    await backend.stop()
    client.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_lane_does_not_poison_another(host):
    backend, client, _ = host
    store = SimpleNamespace(
        backend_binding=AsyncMock(return_value=None), bind_backend=AsyncMock()
    )
    tasks = [
        asyncio.create_task(
            backend.send(
                "hi",
                1,
                AsyncMock(),
                chat_id=c,
                store=store,
                attachment_context=context(c),
            )
        )
        for c in ["bad", "good"]
    ]
    async with asyncio.timeout(2):
        while not all(backend.active_for(c) for c in ["bad", "good"]):
            await asyncio.sleep(0.001)
    backend.active_for("bad")["session"].event("session.error", {})
    with pytest.raises(RuntimeError):
        await tasks[0]
    assert backend.lane("bad").poisoned and not backend.runtime.poisoned
    assert backend.busy("good") and not backend.lane("good").poisoned
    backend.active_for("good")["session"].finish("still works")
    assert (await tasks[1])["text"] == "still works"
    await backend.stop()


@pytest.mark.asyncio
async def test_same_chat_serializes_and_model_in_other_chat_does_not_block(host):
    backend, _, _ = host
    store = SimpleNamespace(
        backend_binding=AsyncMock(return_value=None), bind_backend=AsyncMock()
    )
    tasks = [
        asyncio.create_task(
            backend.send(
                str(i),
                1,
                AsyncMock(),
                chat_id="one",
                store=store,
                attachment_context=context("one"),
            )
        )
        for i in range(2)
    ]
    async with asyncio.timeout(2):
        while not backend.active_for("one"):
            await asyncio.sleep(0.001)
    session = backend.active_for("one")["session"]
    assert session.prompts == ["0"]
    other = backend.lane("other")
    other._session = AsyncMock(
        return_value=SimpleNamespace(
            rpc=SimpleNamespace(
                model=SimpleNamespace(
                    get_current=AsyncMock(return_value={"modelId": "fixture"})
                )
            )
        )
    )
    assert (await backend.model("other", store))["model"]["id"] == "fixture"
    session.finish("first")
    await tasks[0]
    async with asyncio.timeout(2):
        while len(session.prompts) < 2:
            await asyncio.sleep(0.001)
    session.finish("second")
    assert (await tasks[1])["text"] == "second"
    await backend.stop()


@pytest.mark.asyncio
async def test_http_admits_six_chats_and_same_chat_followup(
    aiohttp_client, db, host, monkeypatch
):
    from vibes.routes import agents
    from vibes import followups

    backend, _, _ = host
    followups.reset_state()
    agents.start_ffi_dispatch()
    cfg = SimpleNamespace(
        default_agent="copilot-ffi", agent_name="Fixture", agent_avatar=""
    )
    monkeypatch.setattr(agents, "get_config", lambda: cfg)
    monkeypatch.setattr(agents, "get_db", AsyncMock(return_value=db))
    monkeypatch.setattr(agents, "copilot_backend", backend)
    monkeypatch.setattr(
        agents.agent_attachments, "referenced_media", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(agents, "queue_link_preview_fetch", Mock())
    monkeypatch.setattr(agents, "broadcast_event", AsyncMock())
    app = web.Application()
    agents.setup_routes(app)
    client = await aiohttp_client(app)
    chats = ["default"] + [
        (await SessionStore(db).create("Chat " + str(i)))["id"] for i in range(5)
    ]
    gates = {c: asyncio.Event() for c in chats}
    calls = {c: [] for c in chats}

    async def send(content, thread_id, callback, **kwargs):
        chat = kwargs["chat_id"]
        calls[chat].append(content)
        assert kwargs["attachment_context"]["session_id"] == chat
        if content == "first":
            await gates[chat].wait()
        return {"text": chat + " " + content, "content": [], "cancelled": False}

    monkeypatch.setattr(backend, "send", send)
    try:
        responses = await asyncio.gather(
            *(
                client.post(
                    "/agent/default/message", json={"content": "first", "session_id": c}
                )
                for c in chats
            )
        )
        assert all(r.status == 201 for r in responses)
        async with asyncio.timeout(2):
            while not all(calls.values()):
                await asyncio.sleep(0.001)
        assert len(agents._ffi_tasks) == 6
        response = await client.post(
            "/agent/default/message",
            json={"content": "second", "session_id": "default"},
        )
        assert (await response.json())["queued"] == "followup"
        gates["default"].set()
        async with asyncio.timeout(2):
            while "default" in agents._ffi_tasks:
                await asyncio.sleep(0.001)
        assert calls["default"] == ["first", "second"]
        assert len(agents._ffi_tasks) == 5
        for c in chats[1:]:
            gates[c].set()
        await asyncio.gather(*list(agents._ffi_tasks.values()))
        assert not agents._ffi_tasks
    finally:
        await agents.stop_ffi_dispatch()
        followups.reset_state()
        agents.start_ffi_dispatch()


@pytest.mark.asyncio
async def test_shutdown_cancels_all_lanes_and_stops_native_host_once(host):
    backend, client, created = host
    store = SimpleNamespace(
        backend_binding=AsyncMock(return_value=None), bind_backend=AsyncMock()
    )
    tasks = [
        asyncio.create_task(
            backend.send(
                "wait",
                1,
                AsyncMock(),
                chat_id=str(i),
                store=store,
                attachment_context=context(str(i)),
            )
        )
        for i in range(5)
    ]
    async with asyncio.timeout(2):
        while len(created) < 5 or not all(s.entered.is_set() for s in created):
            await asyncio.sleep(0.001)
    await backend.stop(permanent=True)
    assert all(r["cancelled"] for r in await asyncio.gather(*tasks))
    client.stop.assert_awaited_once()
    assert backend.closing and not backend.lanes
    with pytest.raises(RuntimeError, match="shutting down"):
        await backend.start()


@pytest.mark.asyncio
async def test_cancelled_database_transaction_cannot_rollback_other_chat(db):
    entered, release = asyncio.Event(), asyncio.Event()

    async def bad():
        async with db.transaction() as connection:
            await connection.execute(
                "INSERT INTO chat_sessions(id,name) VALUES ('bad','bad')"
            )
            entered.set()
            await release.wait()

    task = asyncio.create_task(bad())
    await entered.wait()
    good = asyncio.create_task(SessionStore(db).create("Good"))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    saved = await good
    assert await SessionStore(db).get(saved["id"])
    assert await SessionStore(db).get("bad") is None
