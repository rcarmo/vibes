"""Input/media/controls safety tests, synthetic data only."""

import asyncio
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from vibes.copilot_media import validate_media, ModelInputs
from vibes.copilot_client import CopilotBackend
from vibes.sessions import SessionStore


@pytest.mark.asyncio
async def test_media_scope_and_materialisation(db):
    png = io.BytesIO()
    Image.new("RGB", (2, 2)).save(png, format="PNG")
    image = await db.create_media(
        "../../bad.png",
        "image/png",
        png.getvalue(),
        metadata={"source": "composer-upload", "session_id": "default"},
    )
    doc = await db.create_media(
        "../../report.txt",
        "text/plain",
        b"synthetic document",
        metadata={"source": "composer-upload", "session_id": "default"},
    )
    other = await SessionStore(db).create("Other")
    private = await db.create_media(
        "private.txt",
        "text/plain",
        b"private",
        metadata={"source": "composer-upload", "session_id": other["id"]},
    )
    await db.create_interaction(
        {
            "type": "user_message",
            "content": "private",
            "session_id": other["id"],
            "media_ids": [private],
        }
    )
    with pytest.raises(ValueError):
        await validate_media(db, [private], "default")
    items = await validate_media(db, [image, doc], "default")
    inputs = ModelInputs(items)
    result = await inputs.prepare()
    assert result[0]["type"] == "blob" and result[0]["mimeType"] == "image/png"
    assert (
        result[1]["type"] == "selection" and result[1]["text"] == "synthetic document"
    )
    path = Path(result[1]["filePath"])
    assert path.name == "input-1.txt" and path.read_bytes() == b"synthetic document"
    inputs.close()
    assert not path.exists()


@pytest.mark.asyncio
async def test_unknown_and_invalid_media(db):
    for ids in [[999], [True], list(range(1, 10)), "bad"]:
        with pytest.raises(ValueError):
            await validate_media(db, ids, "default")
    bad = await db.create_media(
        "image.png",
        "image/png",
        b"not png",
        metadata={"source": "composer-upload", "session_id": "default"},
    )
    with pytest.raises((ValueError, OSError)):
        await validate_media(db, [bad], "default")
    old = await db.create_media("old.txt", "text/plain", b"not an upload", metadata={})
    with pytest.raises(ValueError):
        await validate_media(db, [old], "default")


@pytest.mark.asyncio
async def test_freeform_is_explicit_bounded_and_single_use(monkeypatch):
    from vibes import copilot_client as mod

    backend = CopilotBackend()
    session = SimpleNamespace(session_id="s")
    backend.active = {
        "session": session,
        "chat_id": "chat",
        "thread_id": 1,
        "turn_id": "t",
        "cancelled": False,
    }
    monkeypatch.setattr(
        mod, "get_config", lambda: SimpleNamespace(permission_timeout=2)
    )
    captured = []

    async def publish(p):
        captured.append(p)

    backend.request_callback = publish
    task = asyncio.create_task(
        backend._question(
            {"question": "What?", "allowFreeform": True}, {"session_id": "s"}
        )
    )
    await asyncio.sleep(0)
    rid = captured[0]["request_id"]
    assert captured[0]["allow_freeform"]
    assert not backend.respond(rid, "freeform", " ")
    assert not backend.respond(rid, "freeform", "x" * 8001)
    assert backend.respond(rid, "freeform", "An answer")
    assert await task == {"answer": "An answer", "wasFreeform": True}
    assert not backend.respond(rid, "freeform", "twice")


@pytest.mark.asyncio
async def test_model_read_switch_and_busy(monkeypatch):
    backend = CopilotBackend()
    api = SimpleNamespace(
        get_current=AsyncMock(
            return_value={"modelId": "next", "reasoningEffort": "high"}
        ),
        switch_to=AsyncMock(),
        list=AsyncMock(
            return_value={
                "list": [
                    {
                        "id": "next",
                        "name": "Next",
                        "supportedReasoningEfforts": ["high"],
                    }
                ]
            }
        ),
    )
    session = SimpleNamespace(session_id="s", rpc=SimpleNamespace(model=api))
    from vibes import copilot_client as mod

    monkeypatch.setattr(
        mod, "get_config", lambda: SimpleNamespace(copilot_start_timeout=2)
    )
    backend.start = AsyncMock()
    backend._session = AsyncMock(return_value=session)
    backend.client = SimpleNamespace(
        rpc=SimpleNamespace(sessions=SimpleNamespace(save=AsyncMock()))
    )
    store = SimpleNamespace(
        backend_binding=AsyncMock(return_value={"conversation_id": "s"}),
        bind_backend=AsyncMock(),
    )
    result = await backend.model(
        "chat", store, {"model_id": "next", "thinking_level": "high"}
    )
    assert result["model"]["id"] == "next"
    assert api.switch_to.call_args.args[0].require_available
    store.bind_backend.assert_awaited_once()
    catalog = await backend.models("chat", store)
    assert catalog["thinking_levels"] == ["high"]
    await backend.turn_lock.acquire()
    try:
        with pytest.raises(RuntimeError):
            await backend.model("chat", store)
    finally:
        backend.turn_lock.release()


@pytest.mark.asyncio
async def test_late_question_cannot_cross_sessions():
    backend = CopilotBackend()
    backend.active = {"session": SimpleNamespace(session_id="one")}
    with pytest.raises(PermissionError):
        await backend._question({"question": "Late"}, {"session_id": "two"})
