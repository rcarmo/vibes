"""Tests for agent route handlers — steering, queue, resolve mode."""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
followups_mod = importlib.import_module("vibes.followups")


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
        agent_avatar="",
        user_name="",
        user_avatar="",
        user_avatar_background="",
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
        agent_avatar="",
        user_name="",
        user_avatar="",
        user_avatar_background="",
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
        agent_avatar="",
        user_name="",
        user_avatar="",
        user_avatar_background="",
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


@pytest.mark.asyncio
async def test_set_turn_panel_state_updates_expanded_flag():
    turn_id = "turn-panel"
    agents_mod._turn_previews[turn_id] = {
        "thread_id": 1,
        "agent_id": "default",
        "draft": "",
        "thought": "",
        "expanded": {"draft": False, "thought": False},
    }
    req = make_mocked_request("POST", f"/agent/turn/{turn_id}/panel", match_info={"turn_id": turn_id})
    req.json = AsyncMock(return_value={"panel": "thought", "expanded": True})
    resp = await agents_mod.set_turn_panel_state(req)
    body = json.loads(resp.body)
    assert resp.status == 200
    assert body["panel"] == "thought"
    assert body["expanded"] is True
    assert agents_mod._is_panel_expanded(turn_id, "thought") is True
    agents_mod._turn_previews.pop(turn_id, None)


@pytest.mark.asyncio
async def test_set_turn_panel_state_invalid_panel():
    turn_id = "turn-panel-invalid"
    agents_mod._turn_previews[turn_id] = {
        "thread_id": 1,
        "agent_id": "default",
        "draft": "",
        "thought": "",
        "expanded": {"draft": False, "thought": False},
    }
    req = make_mocked_request("POST", f"/agent/turn/{turn_id}/panel", match_info={"turn_id": turn_id})
    req.json = AsyncMock(return_value={"panel": "plan", "expanded": True})
    resp = await agents_mod.set_turn_panel_state(req)
    assert resp.status == 400
    agents_mod._turn_previews.pop(turn_id, None)


@pytest.mark.asyncio
async def test_set_turn_panel_state_not_found():
    req = make_mocked_request("POST", "/agent/turn/missing/panel", match_info={"turn_id": "missing"})
    req.json = AsyncMock(return_value={"panel": "draft", "expanded": True})
    resp = await agents_mod.set_turn_panel_state(req)
    assert resp.status == 404


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

    async def set_interaction_thread_id(self, interaction_id, thread_id):
        if interaction_id in self._interactions:
            self._interactions[interaction_id]["data"]["thread_id"] = thread_id
            return True
        return False

    async def get_inflight_thread_id(self):
        return None

    async def get_active_turns(self):
        return []


def _make_send_request(content, agent_id="default", mode=None):
    """Create a mock aiohttp request for send_message."""
    req = make_mocked_request("POST", f"/agents/{agent_id}/message",
                               match_info={"agent_id": agent_id})
    payload = {"content": content}
    if mode is not None:
        payload["mode"] = mode
    req.json = AsyncMock(return_value=payload)
    return req


@pytest.fixture
def mock_deps():
    """Patch all external dependencies of send_message."""
    followups_mod.reset_state()
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
async def test_send_message_busy_defaults_to_queue(mock_deps):
    """Busy submissions should default to queued follow-up behavior."""
    with patch.object(agents_mod, "get_config") as mc:
        mc.return_value.default_agent = "pi"
        mock_deps["db"]._interactions[42] = {"id": 42, "data": {"session_id": "default"}}
        fake_turn = {"turn_id": "turn-1", "thread_id": 42, "agent_id": "default", "started_at": "2026-01-01T00:00:00Z"}
        with patch.object(agents_mod, "is_pi_busy", return_value=True), \
             patch.object(mock_deps["db"], "get_active_turns", new_callable=AsyncMock, return_value=[fake_turn]):
            req = _make_send_request("focus on tests")
            resp = await agents_mod.send_message(req)
            assert resp.status == 201
            body = json.loads(resp.body)
            assert body["queued"] == "followup"
            assert body["thread_id"] == 42
            assert "queued" in body["status"].lower()
            mock_deps["enqueue"].assert_not_called()


@pytest.mark.asyncio
async def test_send_message_explicit_pi_steer_when_busy(mock_deps):
    """Explicit steer mode uses real Pi steering when available."""
    with patch.object(agents_mod, "get_config") as mc:
        mc.return_value.default_agent = "pi"
        mock_deps["db"]._interactions[42] = {"id": 42, "data": {"session_id": "default"}}
        fake_turn = {"turn_id": "turn-1", "thread_id": 42, "agent_id": "default", "started_at": "2026-01-01T00:00:00Z"}
        with patch.object(agents_mod, "is_pi_busy", return_value=True), \
             patch.object(mock_deps["db"], "get_active_turns", new_callable=AsyncMock, return_value=[fake_turn]), \
             patch.object(agents_mod, "send_pi_rpc_fire_and_forget",
                          new_callable=AsyncMock, return_value=True) as mock_steer:
            req = _make_send_request("steer me", mode="steer")
            resp = await agents_mod.send_message(req)
            body = json.loads(resp.body)
            assert body["steered"] is True
            assert body["emulated"] is False
            mock_steer.assert_called_once_with({"type": "steer", "message": "steer me"})


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
async def test_send_message_explicit_acp_steer_is_emulated(mock_deps):
    """ACP steer mode should queue a prioritized steer item."""
    with patch.object(agents_mod, "get_config") as mc:
        mc.return_value.default_agent = "acp"
        mock_deps["db"]._interactions[42] = {"id": 42, "data": {"session_id": "default"}}
        mock_deps["db"]._interactions[7] = {"id": 7, "data": {"session_id": "default"}}
        fake_turn = {"turn_id": "turn-2", "thread_id": 7, "agent_id": "default", "started_at": "2026-01-01T00:00:00Z"}
        with patch.object(agents_mod, "_is_agent_busy", return_value=True), \
             patch.object(mock_deps["db"], "get_active_turns", new_callable=AsyncMock, return_value=[fake_turn]):
            req = _make_send_request("hello", mode="steer")
            resp = await agents_mod.send_message(req)
        body = json.loads(resp.body)
        assert resp.status == 201
        assert body["queued"] == "steer"
        assert body["emulated"] is True
        mock_deps["enqueue"].assert_not_called()


@pytest.mark.asyncio
async def test_send_message_acp_idle_enqueues_turn(mock_deps):
    """ACP mode still starts a normal turn while idle."""
    with patch.object(agents_mod, "get_config") as mc:
        mc.return_value.default_agent = "acp"
        with patch.object(agents_mod, "_is_agent_busy", return_value=False):
            req = _make_send_request("hello")
            resp = await agents_mod.send_message(req)
        assert resp.status == 201
        mock_deps["enqueue"].assert_called_once()


@pytest.mark.asyncio
async def test_queue_remove_route(mock_deps):
    """Queued items can be removed via route."""
    item = followups_mod.queue_followup(thread_id=1, agent_id="default", message_id=5, content="hello")
    req = make_mocked_request("POST", "/agent/queue-remove")
    req.json = AsyncMock(return_value={"row_id": item["row_id"]})
    resp = await agents_mod.remove_queue_item(req)
    body = json.loads(resp.body)
    assert resp.status == 200
    assert body["removed"] is True


@pytest.mark.asyncio
async def test_queue_steer_route_emulates_for_acp(mock_deps):
    """Queued ACP items can be promoted into deferred steering."""
    item = followups_mod.queue_followup(thread_id=3, agent_id="default", message_id=8, content="nudge")
    mock_deps["db"]._interactions[3] = {"id": 3, "data": {"session_id": "default"}}
    fake_turn = {"turn_id": "turn-3", "thread_id": 3, "agent_id": "default", "started_at": "2026-01-01T00:00:00Z"}
    req = make_mocked_request("POST", "/agent/queue-steer")
    req.json = AsyncMock(return_value={"row_id": item["row_id"]})
    with patch.object(agents_mod, "get_config") as mc:
        mc.return_value.default_agent = "acp"
        with patch.object(mock_deps["db"], "get_active_turns", new_callable=AsyncMock, return_value=[fake_turn]):
            resp = await agents_mod.steer_queue_item(req)
    body = json.loads(resp.body)
    assert resp.status == 200
    assert body["queued"] == "steer"
    assert body["item"]["emulated"] is True


@pytest.mark.asyncio
async def test_send_message_invalid_mode(mock_deps):
    """Unknown submit mode is rejected."""
    req = _make_send_request("hello", mode="bogus")
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


@pytest.mark.asyncio
async def test_send_message_invalid_json():
    """Invalid JSON body returns 400."""
    req = make_mocked_request("POST", "/agents/default/message",
                               match_info={"agent_id": "default"})
    req.json = AsyncMock(side_effect=json.JSONDecodeError("bad", "", 0))
    resp = await agents_mod.send_message(req)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_get_agent_queue_lists_items(mock_deps):
    """Queue endpoint returns queued follow-ups."""
    followups_mod.queue_followup(thread_id=9, agent_id="default", message_id=12, content="later")
    req = make_mocked_request("GET", "/agent/queue")
    resp = await agents_mod.get_agent_queue(req)
    body = json.loads(resp.body)
    assert resp.status == 200
    assert len(body["items"]) == 1


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
        mc.return_value.agent_avatar = ""
        mc.return_value.user_name = ""
        mc.return_value.user_avatar = ""
        mc.return_value.user_avatar_background = ""
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
        mc.return_value.agent_avatar = ""
        mc.return_value.user_name = ""
        mc.return_value.user_avatar = ""
        mc.return_value.user_avatar_background = ""
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


# --- Context endpoint tests ---

@pytest.mark.asyncio
async def test_get_agent_context_pi_not_running():
    """Returns null usage when Pi is not running."""
    req = make_mocked_request("GET", "/agent/context")
    with patch.object(agents_mod, "is_pi_running", return_value=False):
        resp = await agents_mod.get_agent_context(req)
    body = json.loads(resp.body)
    assert body == {"tokens": None, "contextWindow": None, "percent": None}


@pytest.mark.asyncio
async def test_get_agent_context_with_usage():
    """Returns context usage from Pi state."""
    req = make_mocked_request("GET", "/agent/context")
    state_resp = {
        "success": True,
        "data": {
            "contextUsage": {"tokens": 15000, "contextWindow": 200000},
        },
    }
    with patch.object(agents_mod, "is_pi_running", return_value=True), \
         patch.object(agents_mod, "inspect_session_stats", new_callable=AsyncMock, return_value=state_resp):
        resp = await agents_mod.get_agent_context(req)
    body = json.loads(resp.body)
    assert body["tokens"] == 15000
    assert body["contextWindow"] == 200000
    assert body["percent"] == 7.5


@pytest.mark.asyncio
async def test_get_agent_context_rpc_failure():
    """Returns null usage when RPC fails."""
    req = make_mocked_request("GET", "/agent/context")
    with patch.object(agents_mod, "is_pi_running", return_value=True), \
         patch.object(agents_mod, "inspect_session_stats", new_callable=AsyncMock, side_effect=Exception("timeout")):
        resp = await agents_mod.get_agent_context(req)
    body = json.loads(resp.body)
    assert body == {"tokens": None, "contextWindow": None, "percent": None}


# --- Models endpoint tests ---

@pytest.mark.asyncio
async def test_get_agent_models_pi_not_running():
    """Returns empty when Pi is not running."""
    req = make_mocked_request("GET", "/agent/models")
    with patch.object(agents_mod, "is_pi_running", return_value=False):
        resp = await agents_mod.get_agent_models(req)
    body = json.loads(resp.body)
    assert body == {"current": None, "models": []}


@pytest.mark.asyncio
async def test_get_agent_models_with_data():
    """Returns current model and available models from Pi state."""
    req = make_mocked_request("GET", "/agent/models")
    state_resp = {
        "success": True,
        "data": {
            "model": {"provider": "anthropic", "id": "claude-sonnet-4"},
        },
    }
    models_resp = {
        "success": True,
        "data": {
            "models": [
                {"provider": "anthropic", "modelId": "claude-sonnet-4"},
                {"provider": "anthropic", "modelId": "claude-opus-4"},
            ],
        },
    }

    async def rpc_side_effect(cmd, **kwargs):
        if cmd.get("type") == "get_state":
            return state_resp
        if cmd.get("type") == "get_available_models":
            return models_resp
        return None

    with patch.object(agents_mod, "is_pi_running", return_value=True), \
         patch.object(agents_mod, "send_rpc_command", new_callable=AsyncMock, side_effect=rpc_side_effect):
        resp = await agents_mod.get_agent_models(req)
    body = json.loads(resp.body)
    assert body["current"] == "anthropic/claude-sonnet-4"
    assert "anthropic/claude-sonnet-4" in body["models"]
    assert "anthropic/claude-opus-4" in body["models"]


@pytest.mark.asyncio
async def test_get_agent_models_rpc_failure():
    """Returns empty when RPC fails."""
    req = make_mocked_request("GET", "/agent/models")
    with patch.object(agents_mod, "is_pi_running", return_value=True), \
         patch.object(agents_mod, "send_rpc_command", new_callable=AsyncMock, side_effect=Exception("timeout")):
        resp = await agents_mod.get_agent_models(req)
    body = json.loads(resp.body)
    assert body == {"current": None, "models": []}


@pytest.mark.asyncio
async def test_queue_promotion_cancel_restores_identity(mock_deps):
    import asyncio
    item = followups_mod.queue_followup(thread_id=1, agent_id='default', message_id=8, content='keep')
    req = MagicMock()
    req.json = AsyncMock(return_value={'row_id': item['row_id']})
    with patch.object(agents_mod, '_resolve_agent_mode', return_value='pi'), \
         patch.object(agents_mod, '_is_agent_busy', return_value=True), \
         patch.object(agents_mod, 'send_pi_rpc_fire_and_forget', AsyncMock(side_effect=asyncio.CancelledError)):
        with pytest.raises(asyncio.CancelledError):
            await agents_mod.steer_queue_item(req)
    assert followups_mod.list_followups()[0]['row_id'] == item['row_id']


@pytest.mark.asyncio
async def test_queue_promotion_idle_pi_is_emulated_and_keeps_id(mock_deps):
    item = followups_mod.queue_followup(thread_id=1, agent_id='default', message_id=8, content='keep')
    req = MagicMock()
    req.json = AsyncMock(return_value={'row_id': item['row_id']})
    with patch.object(agents_mod, '_resolve_agent_mode', return_value='pi'), \
         patch.object(agents_mod, '_is_agent_busy', return_value=False):
        response = await agents_mod.steer_queue_item(req)
    data = json.loads(response.text)
    assert data['item']['emulated'] is True
    assert data['item']['row_id'] == item['row_id']


@pytest.mark.asyncio
async def test_concurrent_queue_promotion_sends_once(mock_deps):
    import asyncio
    item = followups_mod.queue_followup(thread_id=1, agent_id='default', message_id=8, content='once')
    entered, release = asyncio.Event(), asyncio.Event()
    async def send(_):
        entered.set()
        await release.wait()
        return True
    def request():
        req = MagicMock()
        req.json = AsyncMock(return_value={'row_id': item['row_id']})
        return req
    with patch.object(agents_mod, '_resolve_agent_mode', return_value='pi'), \
         patch.object(agents_mod, '_is_agent_busy', return_value=True), \
         patch.object(agents_mod, 'send_pi_rpc_fire_and_forget', AsyncMock(side_effect=send)) as sender:
        first = asyncio.create_task(agents_mod.steer_queue_item(request()))
        await asyncio.wait_for(entered.wait(), 2)
        second = await agents_mod.steer_queue_item(request())
        release.set()
        response = await first
        assert second.status == 404
        assert response.status == 200
        assert sender.await_count == 1


@pytest.mark.asyncio
async def test_nondefault_missing_session_rejected(mock_deps):
    from vibes.sessions import SessionStore
    req = _make_send_request('private')
    req.json = AsyncMock(return_value={'content': 'private', 'session_id': 'other'})
    with patch.object(SessionStore, 'get', AsyncMock(return_value=None)):
        response = await agents_mod.send_message(req)
    assert response.status == 404
    mock_deps['enqueue'].assert_not_called()


@pytest.mark.asyncio
async def test_invalid_session_identity_rejected(mock_deps):
    req = _make_send_request('private')
    req.json = AsyncMock(return_value={'content': 'private', 'session_id': []})
    response = await agents_mod.send_message(req)
    assert response.status == 400
    mock_deps['enqueue'].assert_not_called()


@pytest.mark.asyncio
async def test_background_agent_dispatch_serializes_worker_turns():
    import asyncio
    entered, release = asyncio.Event(), asyncio.Event()
    running = 0
    peak = 0
    order = []
    async def run(thread_id, content, agent_id):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        order.append(thread_id)
        if thread_id == 1:
            entered.set()
            await release.wait()
        running -= 1
    with patch.object(agents_mod, '_agent_dispatch_lock', asyncio.Lock()), \
         patch.object(agents_mod, '_process_agent_response_locked', AsyncMock(side_effect=run)):
        first = asyncio.create_task(agents_mod.process_agent_response(1, 'one', 'default'))
        await entered.wait()
        second = asyncio.create_task(agents_mod.process_agent_response(2, 'two', 'default'))
        await asyncio.sleep(0)
        assert order == [1]
        release.set()
        await asyncio.gather(first, second)
    assert order == [1, 2]
    assert peak == 1


@pytest.mark.asyncio
async def test_nondefault_idle_submission_persists_session(mock_deps):
    from vibes.sessions import SessionStore
    req = _make_send_request('private')
    req.json = AsyncMock(return_value={'content': 'private', 'session_id': 'other'})
    with patch.object(SessionStore, 'get', AsyncMock(return_value={'id': 'other', 'archived': 0})), \
         patch.object(agents_mod, '_is_agent_busy', return_value=False):
        response = await agents_mod.send_message(req)
    assert response.status == 201
    assert mock_deps['db']._interactions[1]['data']['session_id'] == 'other'
    assert mock_deps['enqueue'].called


@pytest.mark.asyncio
async def test_cross_session_busy_submission_rejected_before_storage(mock_deps):
    from vibes.sessions import SessionStore
    mock_deps['db']._interactions[42] = {'id': 42, 'data': {'session_id': 'default'}}
    req = _make_send_request('private')
    req.json = AsyncMock(return_value={'content': 'private', 'session_id': 'other', 'mode': 'steer'})
    with patch.object(SessionStore, 'get', AsyncMock(return_value={'id': 'other', 'archived': 0})), \
         patch.object(agents_mod, '_is_agent_busy', return_value=True), \
         patch.object(agents_mod, '_get_active_turn_for_agent', AsyncMock(return_value={'thread_id': 42})):
        response = await agents_mod.send_message(req)
    assert response.status == 409
    assert mock_deps['db']._counter == 0
    mock_deps['enqueue'].assert_not_called()
