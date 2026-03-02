"""Tests for agent route handlers — steering, queue, resolve mode."""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp.test_utils import make_mocked_request

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) in sys.path:
    sys.path.remove(str(SRC_PATH))
sys.path.insert(0, str(SRC_PATH))

for module_name in list(sys.modules.keys()):
    if module_name == "vibes" or module_name.startswith("vibes."):
        sys.modules.pop(module_name, None)

agents_mod = importlib.import_module("vibes.routes.agents")


# ── _resolve_agent_mode ──────────────────────────────────


def test_resolve_default_returns_config_default():
    with patch.object(agents_mod, "get_config") as mock:
        mock.return_value.default_agent = "pi"
        assert agents_mod._resolve_agent_mode("default") == "pi"


def test_resolve_explicit_pi():
    with patch.object(agents_mod, "get_config") as mock:
        mock.return_value.default_agent = "acp"
        assert agents_mod._resolve_agent_mode("pi") == "pi"


def test_resolve_explicit_acp():
    with patch.object(agents_mod, "get_config") as mock:
        mock.return_value.default_agent = "pi"
        assert agents_mod._resolve_agent_mode("acp") == "acp"


def test_resolve_unknown_falls_back():
    with patch.object(agents_mod, "get_config") as mock:
        mock.return_value.default_agent = "acp"
        assert agents_mod._resolve_agent_mode("unknown-agent") == "acp"


@pytest.mark.asyncio
async def test_list_agents_includes_default_model_for_acp():
    req = make_mocked_request("GET", "/agents")
    cfg = SimpleNamespace(
        default_agent="acp",
        pi_enabled=False,
        acp_agent="claude-sonnet",
        pi_agent="pi-rpc",
        agent_name="Agent",
    )
    with patch.object(agents_mod, "get_config", return_value=cfg), \
         patch.object(agents_mod, "is_acp_running", return_value=True):
        resp = await agents_mod.list_agents(req)
    body = json.loads(resp.body)
    default_agent = body["agents"][0]
    assert default_agent["id"] == "default"
    assert default_agent["model"] == "claude-sonnet"


@pytest.mark.asyncio
async def test_list_agents_includes_default_model_for_pi():
    req = make_mocked_request("GET", "/agents")
    cfg = SimpleNamespace(
        default_agent="pi",
        pi_enabled=False,
        acp_agent="claude-sonnet",
        pi_agent="pi-rpc",
        pi_model="anthropic/claude-sonnet",
        agent_name="Agent",
    )
    with patch.object(agents_mod, "get_config", return_value=cfg), \
         patch.object(agents_mod, "is_pi_running", return_value=True), \
         patch.object(agents_mod, "send_rpc_command", new_callable=AsyncMock, return_value=None):
        resp = await agents_mod.list_agents(req)
    body = json.loads(resp.body)
    default_agent = body["agents"][0]
    assert default_agent["id"] == "default"
    assert default_agent["model"] == "anthropic/claude-sonnet"


@pytest.mark.asyncio
async def test_list_agents_prefers_runtime_pi_model():
    req = make_mocked_request("GET", "/agents")
    cfg = SimpleNamespace(
        default_agent="pi",
        pi_enabled=False,
        acp_agent="claude-sonnet",
        pi_agent="pi-rpc",
        pi_model="anthropic/claude-sonnet",
        agent_name="Agent",
    )
    with patch.object(agents_mod, "get_config", return_value=cfg), \
         patch.object(agents_mod, "is_pi_running", return_value=True), \
         patch.object(agents_mod, "send_rpc_command", new_callable=AsyncMock, return_value={
             "success": True,
             "data": {"model": {"provider": "openai", "modelId": "gpt-5.2"}},
         }):
        resp = await agents_mod.list_agents(req)
    body = json.loads(resp.body)
    default_agent = body["agents"][0]
    assert default_agent["model"] == "openai/gpt-5.2"


@pytest.mark.asyncio
async def test_get_turn_preview_returns_full_draft_and_thought():
    turn_id = "turn-test"
    agents_mod._turn_previews[turn_id] = {
        "thread_id": 1,
        "agent_id": "default",
        "draft": "line1\nline2",
        "thought": "thinking line",
    }
    req = make_mocked_request("GET", f"/agent/turn/{turn_id}", match_info={"turn_id": turn_id})
    resp = await agents_mod.get_turn_preview(req)
    body = json.loads(resp.body)
    assert resp.status == 200
    assert body["turn_id"] == turn_id
    assert body["draft"] == "line1\nline2"
    assert body["thought"] == "thinking line"
    assert body["draft_total_lines"] == agents_mod._estimate_total_lines("line1\nline2")
    assert body["thought_total_lines"] == agents_mod._estimate_total_lines("thinking line")
    agents_mod._turn_previews.pop(turn_id, None)


@pytest.mark.asyncio
async def test_get_turn_preview_not_found():
    req = make_mocked_request("GET", "/agent/turn/unknown", match_info={"turn_id": "unknown"})
    resp = await agents_mod.get_turn_preview(req)
    body = json.loads(resp.body)
    assert resp.status == 404
    assert body["error"] == "Turn not found"


# ── _extract_text_from_blocks ─────────────────────────────


def test_extract_text_from_blocks():
    blocks = [
        {"type": "text", "text": "Hello"},
        {"type": "image", "data": "..."},
        {"type": "text", "text": " World"},
    ]
    result = agents_mod._extract_text_from_blocks(blocks)
    assert result == "Hello World"


def test_extract_text_empty_blocks():
    assert agents_mod._extract_text_from_blocks([]) == ""


def test_extract_text_no_text_blocks():
    blocks = [{"type": "image", "data": "..."}]
    assert agents_mod._extract_text_from_blocks(blocks) == ""


def test_has_meaningful_response_with_text():
    assert agents_mod._has_meaningful_response("hello", [], []) is True


def test_has_meaningful_response_with_media_or_file_block():
    assert agents_mod._has_meaningful_response("", [], [1]) is True
    assert agents_mod._has_meaningful_response("", [{"type": "file", "name": "x.txt"}], []) is True


def test_has_meaningful_response_empty():
    assert agents_mod._has_meaningful_response("", [], []) is False
    assert agents_mod._has_meaningful_response("", [{"type": "text", "text": "   "}], []) is False


# ── send_message steering logic ──────────────────────────
# These tests mock the database, SSE, and agent clients.


class FakeDB:
    """Minimal mock for the database."""
    def __init__(self):
        self._counter = 0
        self._interactions = {}

    async def create_interaction(self, data):
        self._counter += 1
        self._interactions[self._counter] = {
            "id": self._counter,
            "timestamp": "2026-01-01T00:00:00Z",
            "data": data,
        }
        return self._counter

    async def get_interaction(self, msg_id):
        return self._interactions.get(msg_id)


def _make_send_request(content, agent_id="default"):
    """Create a mock aiohttp request for send_message."""
    req = make_mocked_request("POST", f"/agents/{agent_id}/message",
                               match_info={"agent_id": agent_id})
    req.json = AsyncMock(return_value={"content": content})
    return req


@pytest.fixture
def mock_deps():
    """Patch all external dependencies of send_message."""
    fake_db = FakeDB()
    with patch.object(agents_mod, "get_db", new_callable=AsyncMock, return_value=fake_db), \
         patch.object(agents_mod, "broadcast_event", new_callable=AsyncMock) as mock_broadcast, \
         patch.object(agents_mod, "queue_link_preview_fetch"), \
         patch.object(agents_mod, "enqueue") as mock_enqueue:
        yield {
            "db": fake_db,
            "broadcast": mock_broadcast,
            "enqueue": mock_enqueue,
        }


@pytest.mark.asyncio
async def test_send_message_normal_path(mock_deps):
    """Normal message when agent is idle goes to enqueue."""
    with patch.object(agents_mod, "get_config") as mc:
        mc.return_value.default_agent = "pi"
        with patch.object(agents_mod, "is_pi_busy", return_value=False):
            req = _make_send_request("hello world")
            resp = await agents_mod.send_message(req)
            assert resp.status == 201
            body = json.loads(resp.body)
            assert "user_message" in body
            mock_deps["enqueue"].assert_called_once()


@pytest.mark.asyncio
async def test_send_message_steering_when_busy(mock_deps):
    """Message sent while agent is busy should auto-steer."""
    with patch.object(agents_mod, "get_config") as mc:
        mc.return_value.default_agent = "pi"
        with patch.object(agents_mod, "is_pi_busy", return_value=True), \
             patch.object(agents_mod, "send_pi_rpc_fire_and_forget",
                          new_callable=AsyncMock, return_value=True) as mock_steer:
            req = _make_send_request("focus on tests")
            resp = await agents_mod.send_message(req)
            assert resp.status == 201
            body = json.loads(resp.body)
            assert body["steered"] is True
            assert "steering" in body["status"].lower()
            mock_steer.assert_called_once_with({"type": "steer", "message": "focus on tests"})
            # Should NOT enqueue a new turn
            mock_deps["enqueue"].assert_not_called()


@pytest.mark.asyncio
async def test_send_message_steering_failure(mock_deps):
    """Steering failure still returns 201 with steered=False."""
    with patch.object(agents_mod, "get_config") as mc:
        mc.return_value.default_agent = "pi"
        with patch.object(agents_mod, "is_pi_busy", return_value=True), \
             patch.object(agents_mod, "send_pi_rpc_fire_and_forget",
                          new_callable=AsyncMock, return_value=False):
            req = _make_send_request("steer me")
            resp = await agents_mod.send_message(req)
            body = json.loads(resp.body)
            assert body["steered"] is False


@pytest.mark.asyncio
async def test_send_message_slash_command(mock_deps):
    """Slash commands are handled and not forwarded."""
    with patch.object(agents_mod, "get_config") as mc:
        mc.return_value.default_agent = "pi"
        req = _make_send_request("/commands")
        resp = await agents_mod.send_message(req)
        body = json.loads(resp.body)
        assert "command" in body
        assert body["command"]["status"] == "success"
        mock_deps["enqueue"].assert_not_called()


@pytest.mark.asyncio
async def test_send_message_acp_no_steering(mock_deps):
    """ACP mode should not steer, just enqueue normally."""
    with patch.object(agents_mod, "get_config") as mc:
        mc.return_value.default_agent = "acp"
        req = _make_send_request("hello")
        resp = await agents_mod.send_message(req)
        assert resp.status == 201
        mock_deps["enqueue"].assert_called_once()


@pytest.mark.asyncio
async def test_send_message_invalid_json():
    """Invalid JSON body returns 400."""
    req = make_mocked_request("POST", "/agents/default/message",
                               match_info={"agent_id": "default"})
    req.json = AsyncMock(side_effect=json.JSONDecodeError("bad", "", 0))
    resp = await agents_mod.send_message(req)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_send_message_missing_content():
    """Missing content field returns 400."""
    req = make_mocked_request("POST", "/agents/default/message",
                               match_info={"agent_id": "default"})
    req.json = AsyncMock(return_value={"not_content": "x"})
    resp = await agents_mod.send_message(req)
    assert resp.status == 400


# ── list_agents ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_agents_pi_default():
    with patch.object(agents_mod, "get_config") as mc, \
         patch.object(agents_mod, "is_pi_running", return_value=True), \
         patch.object(agents_mod, "is_acp_running", return_value=False), \
         patch.object(agents_mod, "send_rpc_command", new_callable=AsyncMock, return_value=None):
        mc.return_value.default_agent = "pi"
        mc.return_value.pi_agent = "pi-binary"
        mc.return_value.pi_model = "anthropic/claude-sonnet"
        mc.return_value.pi_enabled = True
        mc.return_value.acp_agent = "copilot --acp"
        mc.return_value.agent_name = "TestBot"
        req = make_mocked_request("GET", "/agents")
        resp = await agents_mod.list_agents(req)
        body = json.loads(resp.body)
        agents = body["agents"]
        assert any(a["id"] == "default" and a["name"] == "TestBot" for a in agents)
        assert any(a["id"] == "acp" for a in agents)


@pytest.mark.asyncio
async def test_list_agents_acp_default():
    with patch.object(agents_mod, "get_config") as mc, \
         patch.object(agents_mod, "is_pi_running", return_value=False), \
         patch.object(agents_mod, "is_acp_running", return_value=True):
        mc.return_value.default_agent = "acp"
        mc.return_value.pi_agent = "pi-binary"
        mc.return_value.pi_enabled = True
        mc.return_value.acp_agent = "copilot --acp"
        mc.return_value.agent_name = "TestBot"
        req = make_mocked_request("GET", "/agents")
        resp = await agents_mod.list_agents(req)
        body = json.loads(resp.body)
        agents = body["agents"]
        default_agent = next(a for a in agents if a["id"] == "default")
        assert default_agent["name"] == "TestBot"
        assert default_agent["status"] == "running"
        assert any(a["id"] == "pi" for a in agents)


# ── _extract_and_store_data_uri_images ────────────────────


@pytest.mark.asyncio
async def test_extract_data_uri_no_images():
    db = AsyncMock()
    result = await agents_mod._extract_and_store_data_uri_images(db, "plain text")
    assert result == "plain text"
    db.create_media.assert_not_called()


@pytest.mark.asyncio
async def test_extract_data_uri_none():
    db = AsyncMock()
    result = await agents_mod._extract_and_store_data_uri_images(db, None)
    assert result is None


@pytest.mark.asyncio
async def test_extract_data_uri_replaces_image():
    db = AsyncMock()
    db.create_media = AsyncMock(return_value=42)
    # A minimal valid base64 PNG data URI in markdown
    import base64
    pixel = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    text = f"![chart](data:image/png;base64,{pixel})"
    result = await agents_mod._extract_and_store_data_uri_images(db, text)
    assert "/media/42" in result
    assert "data:image" not in result
    db.create_media.assert_called_once()


# ── _check_whitelist ──────────────────────────────────────


@pytest.mark.asyncio
async def test_check_whitelist_auto_approve():
    with patch.object(agents_mod, "get_config") as mc, \
         patch.object(agents_mod, "get_db", new_callable=AsyncMock) as mock_db:
        mc.return_value.permission_auto_approve = True
        result = await agents_mod._check_whitelist("dangerous_tool")
        assert result is True
        mock_db.assert_not_called()


@pytest.mark.asyncio
async def test_check_whitelist_delegates_to_db():
    mock_db = AsyncMock()
    mock_db.is_whitelisted = AsyncMock(return_value=False)
    with patch.object(agents_mod, "get_config") as mc, \
         patch.object(agents_mod, "get_db", new_callable=AsyncMock, return_value=mock_db):
        mc.return_value.permission_auto_approve = False
        result = await agents_mod._check_whitelist("some_tool")
        assert result is False
        mock_db.is_whitelisted.assert_called_once_with("some_tool")
