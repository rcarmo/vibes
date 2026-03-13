"""Tests for the slash command parser and executor."""

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) in sys.path:
    sys.path.remove(str(SRC_PATH))
sys.path.insert(0, str(SRC_PATH))

for module_name in list(sys.modules.keys()):
    if module_name == "vibes" or module_name.startswith("vibes."):
        sys.modules.pop(module_name, None)

_mod = importlib.import_module("vibes.slash_commands")
parse_command = _mod.parse_command
execute_command = _mod.execute_command
SlashCommand = _mod.SlashCommand
_resolve_theme = _mod._resolve_theme
_normalize_hex = _mod._normalize_hex


# ── parse_command ──────────────────────────────────────────


def test_parse_none_for_empty():
    assert parse_command("") is None
    assert parse_command("   ") is None


def test_parse_none_for_non_slash():
    assert parse_command("hello world") is None
    assert parse_command("not a /command") is None


def test_parse_commands():
    cmd = parse_command("/commands")
    assert cmd is not None
    assert cmd.name == "commands"
    assert cmd.args == ""


def test_parse_restart():
    cmd = parse_command("/restart")
    assert cmd is not None
    assert cmd.name == "restart"


def test_parse_unknown_command():
    cmd = parse_command("/foobar some args")
    assert cmd is not None
    assert cmd.name == "foobar"
    assert cmd.args == "some args"


def test_parse_case_insensitive():
    cmd = parse_command("/COMMANDS")
    assert cmd is not None
    assert cmd.name == "commands"


def test_parse_preserves_raw():
    cmd = parse_command("  /restart  ")
    assert cmd is not None
    assert cmd.raw == "/restart"


# ── execute_command ────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_commands():
    cmd = SlashCommand(name="commands", raw="/commands")
    result = await execute_command(cmd, "acp")
    assert result.status == "success"
    assert result.handled is True
    assert "/restart" in result.message
    assert "/commands" in result.message


@pytest.mark.asyncio
async def test_execute_restart_acp():
    with patch("vibes.acp_client.stop_agent", new_callable=AsyncMock) as mock_stop, \
         patch("vibes.acp_client.start_agent", new_callable=AsyncMock, return_value=True) as mock_start:
        cmd = SlashCommand(name="restart", raw="/restart")
        result = await execute_command(cmd, "acp")
        assert result.status == "success"
        assert result.handled is True
        assert "ACP agent restarted" in result.message
        mock_stop.assert_awaited_once()
        mock_start.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_restart_pi():
    with patch("vibes.pi_client.stop_pi_agent", new_callable=AsyncMock) as mock_stop, \
         patch("vibes.pi_client.start_pi_agent", new_callable=AsyncMock, return_value=True) as mock_start:
        cmd = SlashCommand(name="restart", raw="/restart")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert result.handled is True
        assert "Pi agent restarted" in result.message
        mock_stop.assert_awaited_once()
        mock_start.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_restart_failure():
    with patch("vibes.acp_client.stop_agent", new_callable=AsyncMock), \
         patch("vibes.acp_client.start_agent", new_callable=AsyncMock, return_value=False):
        cmd = SlashCommand(name="restart", raw="/restart")
        result = await execute_command(cmd, "acp")
        assert result.status == "error"
        assert "Failed to restart" in result.message


@pytest.mark.asyncio
async def test_execute_unknown_not_handled():
    cmd = SlashCommand(name="foobar", args="test", raw="/foobar test")
    result = await execute_command(cmd, "acp")
    assert result.handled is False


# ── /model ─────────────────────────────────────────────────


def test_parse_model_no_args():
    cmd = parse_command("/model")
    assert cmd is not None
    assert cmd.name == "model"
    assert cmd.args == ""


def test_parse_model_with_args():
    cmd = parse_command("/model anthropic/claude-sonnet")
    assert cmd.name == "model"
    assert cmd.args == "anthropic/claude-sonnet"


def test_parse_context_alias():
    cmd = parse_command("/ctx")
    assert cmd is not None
    assert cmd.name == "ctx"


@pytest.mark.asyncio
async def test_model_show_pi(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", None)
    monkeypatch.setattr(config, "pi_thinking", None)
    sc = importlib.import_module("vibes.slash_commands")
    monkeypatch.setattr(sc, "_query_pi_models_rpc", AsyncMock(return_value=[]))
    monkeypatch.setattr(sc, "_query_pi_models_cli", AsyncMock(return_value=[]))
    with patch("vibes.pi_client.is_pi_running", return_value=False):
        cmd = SlashCommand(name="model", args="", raw="/model")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "default" in result.message
        assert "/model <provider/model>" in result.message


@pytest.mark.asyncio
async def test_model_show_pi_with_list(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", "anthropic/claude-sonnet")
    monkeypatch.setattr(config, "pi_thinking", None)
    # Patch on _mod (the module object that execute_command was imported from)
    monkeypatch.setattr(_mod, "_query_pi_models_rpc", AsyncMock(return_value=[
        "anthropic/claude-sonnet", "anthropic/claude-haiku", "openai/gpt-4",
    ]))
    monkeypatch.setattr(_mod, "_query_pi_models_cli", AsyncMock(return_value=[]))
    # Also need to patch is_pi_running where _show_pi_model_info imports it
    # _show_pi_model_info does: from .pi_client import is_pi_running
    # This resolves to the pi_client that vibes.slash_commands originally imported
    pi_client_mod = sys.modules.get("vibes.pi_client")
    if pi_client_mod:
        monkeypatch.setattr(pi_client_mod, "is_pi_running", lambda: False)
    cmd = SlashCommand(name="model", args="", raw="/model")
    result = await execute_command(cmd, "pi")
    assert result.status == "success"
    assert "Available models:" in result.message
    assert "`anthropic/claude-sonnet` *(current)*" in result.message
    assert "openai/gpt-4" in result.message


@pytest.mark.asyncio
async def test_model_show_pi_prefers_model_id_from_state(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", None)
    monkeypatch.setattr(config, "pi_thinking", None)
    monkeypatch.setattr(_mod, "_query_pi_models_rpc", AsyncMock(return_value=[]))
    monkeypatch.setattr(_mod, "_query_pi_models_cli", AsyncMock(return_value=[]))
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock, return_value={
             "success": True,
             "data": {
                 "model": {"provider": "openai", "name": "GPT-4.1", "modelId": "gpt-4.1"},
                 "thinkingLevel": "low",
             },
         }):
        cmd = SlashCommand(name="model", args="", raw="/model")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "Current model: openai/gpt-4.1" in result.message
        assert "Thinking level: low" in result.message


@pytest.mark.asyncio
async def test_model_show_acp():
    cmd = SlashCommand(name="model", args="", raw="/model")
    result = await execute_command(cmd, "acp")
    assert result.status == "success"
    assert "ACP agent" in result.message


@pytest.mark.asyncio
async def test_model_set_acp_not_supported():
    cmd = SlashCommand(name="model", args="some-model", raw="/model some-model")
    result = await execute_command(cmd, "acp")
    assert result.status == "error"
    assert "not supported" in result.message


@pytest.mark.asyncio
async def test_model_set_pi(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", None)
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock,
               return_value={"type": "response", "command": "set_model", "success": True, "data": {"name": "claude-sonnet"}}):
        cmd = SlashCommand(name="model", args="anthropic/claude-sonnet", raw="/model anthropic/claude-sonnet")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "claude-sonnet" in result.message
        assert config.pi_model == "anthropic/claude-sonnet"


@pytest.mark.asyncio
async def test_models_alias_uses_model(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", None)
    monkeypatch.setattr(config, "pi_thinking", None)
    monkeypatch.setattr(_mod, "_query_pi_models_rpc", AsyncMock(return_value=[]))
    monkeypatch.setattr(_mod, "_query_pi_models_cli", AsyncMock(return_value=[]))
    with patch("vibes.pi_client.is_pi_running", return_value=False):
        cmd = SlashCommand(name="models", args="", raw="/models")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "Current model:" in result.message


@pytest.mark.asyncio
async def test_cycle_model_back(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", "b/two")
    monkeypatch.setattr(_mod, "_query_pi_models_rpc", AsyncMock(return_value=["a/one", "b/two", "c/three"]))
    monkeypatch.setattr(_mod, "_query_pi_models_cli", AsyncMock(return_value=[]))
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock, side_effect=[
             {"type": "response", "command": "set_model", "success": True, "data": {"provider": "a", "modelId": "one"}},
             {"type": "response", "command": "get_state", "success": True, "data": {}},
         ]):
        cmd = SlashCommand(name="cycle-model", args="back", raw="/cycle-model back")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "Model set to `a/one`" in result.message


# ── /thinking ──────────────────────────────────────────────


def test_parse_thinking():
    cmd = parse_command("/thinking high")
    assert cmd.name == "thinking"
    assert cmd.args == "high"


@pytest.mark.asyncio
async def test_thinking_show_pi(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_thinking", "medium")
    monkeypatch.setattr(config, "pi_model", None)
    cmd = SlashCommand(name="thinking", args="", raw="/thinking")
    result = await execute_command(cmd, "pi")
    assert result.status == "success"
    assert "medium" in result.message
    assert "Available levels" in result.message


@pytest.mark.asyncio
async def test_thinking_acp_not_supported():
    cmd = SlashCommand(name="thinking", args="high", raw="/thinking high")
    result = await execute_command(cmd, "acp")
    assert result.status == "error"
    assert "not supported" in result.message


@pytest.mark.asyncio
async def test_thinking_invalid_level():
    cmd = SlashCommand(name="thinking", args="turbo", raw="/thinking turbo")
    result = await execute_command(cmd, "pi")
    assert result.status == "error"
    assert "Unknown thinking level" in result.message
    assert "turbo" in result.message


@pytest.mark.asyncio
async def test_thinking_set_pi(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_thinking", None)
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock,
               return_value={"type": "response", "command": "set_thinking_level", "success": True}):
        cmd = SlashCommand(name="thinking", args="high", raw="/thinking high")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "high" in result.message
        assert config.pi_thinking == "high"


@pytest.mark.asyncio
async def test_thinking_set_off_clears(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_thinking", "high")
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock,
               return_value={"type": "response", "command": "set_thinking_level", "success": True}):
        cmd = SlashCommand(name="thinking", args="off", raw="/thinking off")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert config.pi_thinking is None


@pytest.mark.asyncio
async def test_cycle_thinking(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_thinking", "low")
    monkeypatch.setattr(config, "pi_model", "openai/gpt-4.1")
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock,
               return_value={"type": "response", "command": "set_thinking_level", "success": True}):
        cmd = SlashCommand(name="cycle-thinking", args="", raw="/cycle-thinking")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "Thinking level set to `medium`." in result.message
        assert config.pi_thinking == "medium"


@pytest.mark.asyncio
async def test_commands_lists_all():
    cmd = SlashCommand(name="commands", raw="/commands")
    result = await execute_command(cmd, "acp")
    assert "/model" in result.message
    assert "/thinking" in result.message
    assert "/steer" not in result.message
    assert "/queue" in result.message
    assert "/abort" in result.message


# ── /shell ─────────────────────────────────────────────────


def test_parse_shell_command():
    cmd = parse_command("/shell echo hello")
    assert cmd is not None
    assert cmd.name == "shell"
    assert cmd.args == "echo hello"


@pytest.mark.asyncio
async def test_shell_no_args():
    cmd = SlashCommand(name="shell", args="", raw="/shell")
    result = await execute_command(cmd, "acp")
    assert result.status == "error"
    assert "Usage" in result.message


@pytest.mark.asyncio
async def test_shell_success():
    cmd = SlashCommand(name="shell", args="echo hello", raw="/shell echo hello")
    result = await execute_command(cmd, "acp")
    assert result.status == "success"
    assert result.handled is True
    assert "```" in result.message
    assert "hello" in result.message
    assert "[ok]" in result.message


@pytest.mark.asyncio
async def test_shell_failure():
    cmd = SlashCommand(name="shell", args="false", raw="/shell false")
    result = await execute_command(cmd, "acp")
    assert result.status == "error"
    assert result.handled is True
    assert "exit code" in result.message


@pytest.mark.asyncio
async def test_shell_stderr_merged():
    cmd = SlashCommand(name="shell", args="echo err >&2", raw="/shell echo err >&2")
    result = await execute_command(cmd, "acp")
    assert result.handled is True
    assert "err" in result.message


@pytest.mark.asyncio
async def test_bash_alias_note():
    cmd = SlashCommand(name="bash", args="echo hi", raw="/bash echo hi")
    result = await execute_command(cmd, "acp")
    assert result.status == "success"
    assert "does not store hidden tool context" in result.message


@pytest.mark.asyncio
async def test_shell_timeout(monkeypatch):
    import subprocess as _subprocess
    import vibes.slash_commands as sc

    monkeypatch.setattr(sc, "SHELL_TIMEOUT", 0.05)

    def fake_run(*a, **kw):
        raise _subprocess.TimeoutExpired(cmd="sleep 60", timeout=0.05)

    monkeypatch.setattr(_subprocess, "run", fake_run)
    cmd = SlashCommand(name="shell", args="sleep 60", raw="/shell sleep 60")
    result = await execute_command(cmd, "acp")
    assert result.status == "error"
    assert "timed out" in result.message


@pytest.mark.asyncio
async def test_shell_commands_listed():
    cmd = SlashCommand(name="commands", raw="/commands")
    result = await execute_command(cmd, "acp")
    assert "/shell" in result.message


# ── error path coverage ────────────────────────────────────


@pytest.mark.asyncio
async def test_restart_exception():
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock, side_effect=RuntimeError("boom")), \
         patch("vibes.pi_client.stop_pi_agent", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
        cmd = SlashCommand(name="restart", raw="/restart")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "boom" in result.message


@pytest.mark.asyncio
async def test_model_set_pi_rpc_failure(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", None)
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock,
               return_value={"type": "response", "command": "set_model", "success": False, "error": "unknown model"}):
        cmd = SlashCommand(name="model", args="x/y", raw="/model x/y")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "unknown model" in result.message


@pytest.mark.asyncio
async def test_model_set_pi_not_running(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", None)
    with patch("vibes.pi_client.is_pi_running", return_value=False):
        cmd = SlashCommand(name="model", args="x/y", raw="/model x/y")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "not running" in result.message


@pytest.mark.asyncio
async def test_thinking_set_pi_rpc_failure(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_thinking", None)
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock,
               return_value={"type": "response", "command": "set_thinking_level", "success": False, "error": "bad level"}):
        cmd = SlashCommand(name="thinking", args="high", raw="/thinking high")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "bad level" in result.message


@pytest.mark.asyncio
async def test_thinking_set_pi_not_running(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_thinking", None)
    with patch("vibes.pi_client.is_pi_running", return_value=False):
        cmd = SlashCommand(name="thinking", args="high", raw="/thinking high")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "not running" in result.message


# ── /abort ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_abort_pi():
    with patch("vibes.pi_client.send_rpc_fire_and_forget", new_callable=AsyncMock, return_value=True):
        cmd = SlashCommand(name="abort", args="", raw="/abort")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "Abort" in result.message


@pytest.mark.asyncio
async def test_abort_not_running():
    with patch("vibes.pi_client.send_rpc_fire_and_forget", new_callable=AsyncMock, return_value=False):
        cmd = SlashCommand(name="abort", args="", raw="/abort")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "not running" in result.message


@pytest.mark.asyncio
async def test_abort_acp_not_supported():
    cmd = SlashCommand(name="abort", args="", raw="/abort")
    result = await execute_command(cmd, "acp")
    assert result.status == "error"
    assert "only supported" in result.message


# ── /steer ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_queue_pi_busy():
    with patch("vibes.pi_client.is_busy", return_value=True):
        cmd = SlashCommand(name="queue", args="do the tests next", raw="/queue do the tests next")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "queued" in result.message.lower()
        assert "do the tests next" in result.message


@pytest.mark.asyncio
async def test_queue_no_args():
    cmd = SlashCommand(name="queue", args="", raw="/queue")
    result = await execute_command(cmd, "pi")
    assert result.status == "error"
    assert "Usage" in result.message


@pytest.mark.asyncio
async def test_queue_idle():
    with patch("vibes.pi_client.is_busy", return_value=False):
        cmd = SlashCommand(name="queue", args="do X", raw="/queue do X")
        result = await execute_command(cmd, "pi")
        assert "idle" in result.message.lower()


@pytest.mark.asyncio
async def test_queue_acp_not_supported():
    cmd = SlashCommand(name="queue", args="do X", raw="/queue do X")
    result = await execute_command(cmd, "acp")
    assert result.status == "error"
    assert "only supported" in result.message


@pytest.mark.asyncio
async def test_shell_generic_exception(monkeypatch):
    import subprocess as _subprocess

    def _boom(*a, **kw):
        raise OSError("no such file")

    monkeypatch.setattr(_subprocess, "run", _boom)
    cmd = SlashCommand(name="shell", args="echo hi", raw="/shell echo hi")
    result = await execute_command(cmd, "acp")
    assert result.status == "error"
    assert "Shell error" in result.message


@pytest.mark.asyncio
async def test_prompt_show_empty():
    cmd = SlashCommand(name="prompt", args="", raw="/prompt")
    result = await execute_command(cmd, "pi")
    assert result.status == "success"
    assert "No user prompt set" in result.message


@pytest.mark.asyncio
async def test_prompt_set():
    cmd = SlashCommand(name="prompt", args="Be concise", raw="/prompt Be concise")
    result = await execute_command(cmd, "pi")
    assert result.status == "success"
    assert "Be concise" in result.message

    # Verify it shows up
    cmd2 = SlashCommand(name="prompt", args="", raw="/prompt")
    result2 = await execute_command(cmd2, "pi")
    assert "Be concise" in result2.message

    # Clear it
    cmd3 = SlashCommand(name="prompt", args="clear", raw="/prompt clear")
    result3 = await execute_command(cmd3, "pi")
    assert "cleared" in result3.message

    # Verify cleared
    cmd4 = SlashCommand(name="prompt", args="", raw="/prompt")
    result4 = await execute_command(cmd4, "pi")
    assert "No user prompt set" in result4.message


@pytest.mark.asyncio
async def test_prompt_listed_in_commands():
    cmd = SlashCommand(name="commands", args="", raw="/commands")
    result = await execute_command(cmd, "pi")
    assert "/prompt" in result.message


@pytest.mark.asyncio
async def test_prompt_works_in_acp_mode():
    cmd = SlashCommand(name="prompt", args="Be brief", raw="/prompt Be brief")
    result = await execute_command(cmd, "acp")
    assert result.status == "success"
    assert "Be brief" in result.message
    # Clean up
    await execute_command(SlashCommand(name="prompt", args="clear", raw="/prompt clear"), "acp")


@pytest.mark.asyncio
async def test_context_pi():
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock, return_value={
             "success": True,
             "data": {
                 "context": {"tokens": 1200, "contextWindow": 8000},
                 "model": {"provider": "openai", "modelId": "gpt-4.1"},
             },
         }):
        cmd = SlashCommand(name="context", args="", raw="/context")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "1200" in result.message
        assert "8000" in result.message


@pytest.mark.asyncio
async def test_ctx_alias_acp():
    cmd = SlashCommand(name="ctx", args="", raw="/ctx")
    result = await execute_command(cmd, "acp")
    assert result.status == "success"
    assert "only available for Pi agents" in result.message


@pytest.mark.asyncio
async def test_state_acp(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "agent_name", "TestAgent")
    monkeypatch.setattr(config, "acp_agent", "codex-acp")
    monkeypatch.setattr(config, "prompt", "")
    monkeypatch.setattr(config, "user_name", "")
    cmd = SlashCommand(name="state", args="", raw="/state")
    result = await execute_command(cmd, "acp")
    assert result.status == "success"
    assert "Agent mode: `acp`" in result.message
    assert "ACP agent: `codex-acp`" in result.message


@pytest.mark.asyncio
async def test_state_pi_with_context(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "agent_name", "TestAgent")
    monkeypatch.setattr(config, "pi_model", "openai/gpt-4.1")
    monkeypatch.setattr(config, "pi_thinking", "low")
    monkeypatch.setattr(config, "prompt", "Be concise")
    monkeypatch.setattr(config, "user_name", "You")
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock, return_value={
             "success": True,
             "data": {"context": {"tokens": 42, "contextWindow": 100}},
         }):
        cmd = SlashCommand(name="state", args="", raw="/state")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "Agent mode: `pi`" in result.message
        assert "Thinking level: `low`" in result.message
        assert "Context: `42` / `100` tokens (42.0%)" in result.message


# ── /name ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_name_show():
    cmd = SlashCommand(name="name", args="", raw="/name")
    result = await execute_command(cmd, "pi")
    assert result.status == "success"
    assert "Agent name" in result.message


@pytest.mark.asyncio
async def test_name_set():
    cmd = SlashCommand(name="name", args="HAL 9000", raw="/name HAL 9000")
    result = await execute_command(cmd, "pi")
    assert result.status == "success"
    assert "HAL 9000" in result.message
    from vibes.config import get_config
    assert get_config().agent_name == "HAL 9000"
    # Clean up
    await execute_command(SlashCommand(name="name", args="clear", raw="/name clear"), "pi")


@pytest.mark.asyncio
async def test_name_clear():
    # Set a name first
    await execute_command(SlashCommand(name="name", args="TestBot", raw="/name TestBot"), "pi")
    cmd = SlashCommand(name="name", args="clear", raw="/name clear")
    result = await execute_command(cmd, "pi")
    assert result.status == "success"
    assert "reset" in result.message.lower()


@pytest.mark.asyncio
async def test_name_listed_in_commands():
    cmd = SlashCommand(name="commands", raw="/commands")
    result = await execute_command(cmd, "pi")
    assert "/name" in result.message


# ── _query_pi_models_rpc ─────────────────────────────────


@pytest.mark.asyncio
async def test_query_models_rpc_not_running():
    with patch("vibes.pi_client.is_pi_running", return_value=False):
        result = await _mod._query_pi_models_rpc()
        assert result == []


@pytest.mark.asyncio
async def test_query_models_rpc_success():
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock, return_value={
             "success": True,
             "data": {
                 "models": [
                     {"provider": "openai", "name": "gpt-4"},
                     {"provider": "anthropic", "modelId": "claude-3"},
                     {"provider": "", "name": "local-model"},
                 ]
             }
         }):
        result = await _mod._query_pi_models_rpc()
        assert "anthropic/claude-3" in result
        assert "openai/gpt-4" in result
        assert "local-model" in result
        assert result == sorted(result)


@pytest.mark.asyncio
async def test_query_models_rpc_prefers_model_id_over_name():
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock, return_value={
             "success": True,
             "data": {
                 "models": [
                     {"provider": "openai", "name": "GPT-4.1 label", "modelId": "gpt-4.1"},
                 ]
             }
         }):
        result = await _mod._query_pi_models_rpc()
        assert "openai/gpt-4.1" in result
        assert "openai/GPT-4.1 label" not in result


@pytest.mark.asyncio
async def test_query_models_rpc_failure():
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock, return_value={
             "success": False, "error": "not supported"
         }):
        result = await _mod._query_pi_models_rpc()
        assert result == []


@pytest.mark.asyncio
async def test_query_models_rpc_exception():
    with patch("vibes.pi_client.is_pi_running", return_value=True), \
         patch("vibes.pi_client.send_rpc_command", new_callable=AsyncMock,
               side_effect=ConnectionError("broken")):
        result = await _mod._query_pi_models_rpc()
        assert result == []


# ── _query_pi_models_cli ─────────────────────────────────


@pytest.mark.asyncio
async def test_query_models_cli_no_executable(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_agent", "nonexistent-binary-xyz")
    result = await _mod._query_pi_models_cli(config)
    assert result == []


@pytest.mark.asyncio
async def test_query_models_cli_empty_command(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_agent", "")
    result = await _mod._query_pi_models_cli(config)
    assert result == []


@pytest.mark.asyncio
async def test_query_models_cli_parses_output(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_agent", "echo")

    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(
        b"Provider  Model\nopenai    gpt-4\nanthropic claude-3\n", b""
    ))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc), \
         patch("shutil.which", return_value="/usr/bin/echo"):
        result = await _mod._query_pi_models_cli(config)
        assert "openai/gpt-4" in result
        assert "anthropic/claude-3" in result


# ── _handle_thinking ──────────────────────────────────────


@pytest.mark.asyncio
async def test_thinking_show_current():
    cmd = SlashCommand(name="thinking", args="", raw="/thinking")
    result = await execute_command(cmd, "pi")
    assert result.status == "success"
    assert "Current thinking level:" in result.message
    assert "Available levels:" in result.message


@pytest.mark.asyncio
async def test_thinking_invalid_level_extreme():
    cmd = SlashCommand(name="thinking", args="extreme", raw="/thinking extreme")
    result = await execute_command(cmd, "pi")
    assert result.status == "error"
    assert "Unknown thinking level" in result.message


@pytest.mark.asyncio
async def test_thinking_acp_unsupported():
    cmd = SlashCommand(name="thinking", args="high", raw="/thinking high")
    result = await execute_command(cmd, "acp")
    assert result.status == "error"
    assert "not supported" in result.message


@pytest.mark.asyncio
async def test_thinking_set_not_running():
    with patch("vibes.pi_client.is_pi_running", return_value=False):
        cmd = SlashCommand(name="thinking", args="high", raw="/thinking high")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "not running" in result.message


# ── theme / tint ─────────────────────────────────────────


def test_resolve_theme_canonical():
    assert _resolve_theme("monokai") == "monokai"
    assert _resolve_theme("default") == "default"
    assert _resolve_theme("  Nord  ") == "nord"


def test_resolve_theme_aliases():
    assert _resolve_theme("drac") == "dracula"
    assert _resolve_theme("catpp") == "catppuccin"
    assert _resolve_theme("gruv") == "gruvbox"
    assert _resolve_theme("auto") == "default"
    assert _resolve_theme("tokyo-night") == "tokyo"
    assert _resolve_theme("github-dark") == "github"


def test_resolve_theme_unknown():
    assert _resolve_theme("nope") is None
    assert _resolve_theme("") is None


def test_normalize_hex_valid():
    assert _normalize_hex("#3b82f6") == "#3b82f6"
    assert _normalize_hex("3b82f6") == "#3b82f6"
    assert _normalize_hex("#f00") == "#ff0000"
    assert _normalize_hex("ABC") == "#aabbcc"


def test_normalize_hex_invalid():
    assert _normalize_hex("xyz") is None
    assert _normalize_hex("#12345") is None
    assert _normalize_hex("") is None


@pytest.mark.asyncio
async def test_theme_list():
    with patch("vibes.routes.sse.broadcast_event", new_callable=AsyncMock):
        cmd = SlashCommand(name="theme", args="", raw="/theme")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "monokai" in result.message
        assert "dracula" in result.message


@pytest.mark.asyncio
async def test_theme_set_known():
    with patch("vibes.routes.sse.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
        cmd = SlashCommand(name="theme", args="dracula", raw="/theme dracula")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "dracula" in result.message
        mock_broadcast.assert_called_once_with("ui_theme", {"theme": "dracula"})


@pytest.mark.asyncio
async def test_theme_set_alias():
    with patch("vibes.routes.sse.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
        cmd = SlashCommand(name="theme", args="drac", raw="/theme drac")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        mock_broadcast.assert_called_once_with("ui_theme", {"theme": "dracula"})


@pytest.mark.asyncio
async def test_theme_unknown():
    with patch("vibes.routes.sse.broadcast_event", new_callable=AsyncMock):
        cmd = SlashCommand(name="theme", args="nope", raw="/theme nope")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "Unknown" in result.message


@pytest.mark.asyncio
async def test_tint_set_hex():
    with patch("vibes.routes.sse.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
        cmd = SlashCommand(name="tint", args="#3b82f6", raw="/tint #3b82f6")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        mock_broadcast.assert_called_once_with("ui_theme", {"tint": "#3b82f6"})


@pytest.mark.asyncio
async def test_tint_set_named():
    with patch("vibes.routes.sse.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
        cmd = SlashCommand(name="tint", args="orange", raw="/tint orange")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        mock_broadcast.assert_called_once_with("ui_theme", {"tint": "orange"})


@pytest.mark.asyncio
async def test_tint_clear():
    for word in ("off", "clear", "none", "reset", "default"):
        with patch("vibes.routes.sse.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
            cmd = SlashCommand(name="tint", args=word, raw=f"/tint {word}")
            result = await execute_command(cmd, "pi")
            assert result.status == "success"
            mock_broadcast.assert_called_once_with("ui_theme", {"tint": None})


@pytest.mark.asyncio
async def test_tint_no_args():
    with patch("vibes.routes.sse.broadcast_event", new_callable=AsyncMock):
        cmd = SlashCommand(name="tint", args="", raw="/tint")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "Usage" in result.message


@pytest.mark.asyncio
async def test_tint_invalid_hex():
    with patch("vibes.routes.sse.broadcast_event", new_callable=AsyncMock):
        cmd = SlashCommand(name="tint", args="#xyz", raw="/tint #xyz")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "Invalid" in result.message
