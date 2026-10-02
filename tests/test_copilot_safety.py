"""Offline regression gates for FFI request lifetime and upload isolation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import FormData, web
from vibes.copilot_client import CopilotBackend
from vibes.copilot_media import validate_media
from vibes.sessions import SessionStore


@pytest.mark.asyncio
async def test_request_close_is_scoped_and_timeout_does_not_end_turn(monkeypatch):
    from vibes import copilot_client as mod

    monkeypatch.setattr(
        mod, "get_config", lambda: SimpleNamespace(permission_timeout=0.01)
    )
    backend = CopilotBackend()
    backend.active = {
        "chat_id": "chat",
        "thread_id": 1,
        "turn_id": "turn",
        "cancelled": False,
    }
    backend.request_callback = AsyncMock()
    backend.request_closed_callback = AsyncMock()
    assert await backend._decision("test", {}, [{"optionId": "allow"}]) == "deny"
    event = backend.request_closed_callback.call_args.args[0]
    assert (
        event["reason"] == "timeout"
        and event["session_id"] == "chat"
        and event["turn_id"] == "turn"
    )
    assert not backend.active["cancelled"]
    assert not backend.respond(event["request_id"], "allow")


@pytest.mark.asyncio
async def test_concurrent_prompts_and_abort_deny_every_pending_request(monkeypatch):
    from vibes import copilot_client as mod

    monkeypatch.setattr(
        mod, "get_config", lambda: SimpleNamespace(permission_timeout=2)
    )
    backend = CopilotBackend()
    owner = {
        "chat_id": "chat",
        "thread_id": 1,
        "turn_id": "turn",
        "cancelled": False,
        "session": SimpleNamespace(abort=AsyncMock()),
    }
    backend.active = owner
    backend.request_callback = AsyncMock()
    backend.request_closed_callback = AsyncMock()
    tasks = [
        asyncio.create_task(backend._decision(str(i), {}, [{"optionId": "allow"}]))
        for i in range(2)
    ]
    await asyncio.sleep(0)
    pending = backend.pending_requests("chat")
    assert len(pending) == 2 and backend.pending_requests("other") == []
    assert await backend.abort("chat", owner)
    assert await asyncio.gather(*tasks) == ["deny", "deny"]
    assert not backend.pending_requests("chat")
    assert all(not backend.respond(p["request_id"], "allow") for p in pending)
    assert backend.request_closed_callback.await_count == 2


@pytest.mark.asyncio
async def test_unreferenced_uploads_are_bound_at_upload(
    aiohttp_client, db, monkeypatch
):
    from vibes.routes import media

    monkeypatch.setattr(media, "get_db", AsyncMock(return_value=db))
    app = web.Application()
    media.setup_routes(app)
    client = await aiohttp_client(app)
    other = await SessionStore(db).create("Other")
    form = FormData()
    form.add_field("file", b"synthetic", filename="file.txt", content_type="text/plain")
    response = await client.post("/media/upload?session_id=" + other["id"], data=form)
    assert response.status == 201
    item = await response.json()
    assert item["metadata"]["session_id"] == other["id"]
    assert await validate_media(db, [item["id"]], other["id"])
    with pytest.raises(ValueError):
        await validate_media(db, [item["id"]], "default")
    # Referencing someone else's upload must not launder its ownership.
    await db.create_interaction(
        {"type": "user_message", "content": "reference", "media_ids": [item["id"]]}
    )
    with pytest.raises(ValueError):
        await validate_media(db, [item["id"]], "default")
    assert (await client.post("/media/upload?session_id=missing")).status == 404


@pytest.mark.asyncio
async def test_unscoped_legacy_upload_is_rejected_until_exclusively_referenced(db):
    media = await db.create_media(
        "old.txt", "text/plain", b"old", metadata={"source": "composer-upload"}
    )
    with pytest.raises(ValueError):
        await validate_media(db, [media], "default")
    await db.create_interaction(
        {"type": "user_message", "content": "old", "media_ids": [media]}
    )
    assert await validate_media(db, [media], "default")
    other = await SessionStore(db).create("Other")
    await db.create_interaction(
        {
            "type": "user_message",
            "content": "mixed",
            "media_ids": [media],
            "session_id": other["id"],
        }
    )
    with pytest.raises(ValueError):
        await validate_media(db, [media], "default")


@pytest.mark.parametrize(
    "settings",
    [
        {"copilot_available_tools": ["*"]},
        {"copilot_available_tools": ["builtin:*"]},
        {"copilot_available_tools": ["mcp:server-?"]},
        {"copilot_available_tools": ["view"]},
        {"copilot_mcp_servers": {"test": {"tools": ["read*"]}}},
        {"copilot_mcp_servers": {"test": {"tools": [True]}}},
    ],
)
def test_config_rejects_wildcards_and_invalid_tool_selectors(monkeypatch, settings):
    from vibes import config

    monkeypatch.setattr(config, "_load_settings_file", lambda: settings)
    with pytest.raises(ValueError):
        config.Config()
