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


@pytest.mark.asyncio
async def test_model_show_pi(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", None)
    monkeypatch.setattr(config, "pi_thinking", None)
    cmd = SlashCommand(name="model", args="", raw="/model")
    result = await execute_command(cmd, "pi")
    assert result.status == "success"
    assert "(default)" in result.message


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
    with patch("vibes.pi_client.stop_pi_agent", new_callable=AsyncMock), \
         patch("vibes.pi_client.start_pi_agent", new_callable=AsyncMock, return_value=True):
        cmd = SlashCommand(name="model", args="anthropic/claude-sonnet", raw="/model anthropic/claude-sonnet")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "anthropic/claude-sonnet" in result.message
        assert config.pi_model == "anthropic/claude-sonnet"


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
    with patch("vibes.pi_client.stop_pi_agent", new_callable=AsyncMock), \
         patch("vibes.pi_client.start_pi_agent", new_callable=AsyncMock, return_value=True):
        cmd = SlashCommand(name="thinking", args="high", raw="/thinking high")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert "high" in result.message
        assert config.pi_thinking == "high"


@pytest.mark.asyncio
async def test_thinking_set_off_clears(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_thinking", "high")
    with patch("vibes.pi_client.stop_pi_agent", new_callable=AsyncMock), \
         patch("vibes.pi_client.start_pi_agent", new_callable=AsyncMock, return_value=True):
        cmd = SlashCommand(name="thinking", args="off", raw="/thinking off")
        result = await execute_command(cmd, "pi")
        assert result.status == "success"
        assert config.pi_thinking is None


@pytest.mark.asyncio
async def test_commands_lists_model_and_thinking():
    cmd = SlashCommand(name="commands", raw="/commands")
    result = await execute_command(cmd, "acp")
    assert "/model" in result.message
    assert "/thinking" in result.message


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
async def test_shell_timeout(monkeypatch):
    import asyncio as _asyncio
    import vibes.slash_commands as sc

    monkeypatch.setattr(sc, "SHELL_TIMEOUT", 0.05)

    class FakeProc:
        def kill(self): pass
        async def wait(self): pass
        async def communicate(self):
            await _asyncio.sleep(999)

    async def fake_shell(*a, **kw):
        return FakeProc()

    monkeypatch.setattr(_asyncio, "create_subprocess_shell", fake_shell)
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
    with patch("vibes.pi_client.stop_pi_agent", new_callable=AsyncMock, side_effect=RuntimeError("boom")):
        cmd = SlashCommand(name="restart", raw="/restart")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "boom" in result.message


@pytest.mark.asyncio
async def test_model_set_pi_restart_exception(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", None)
    with patch("vibes.pi_client.stop_pi_agent", new_callable=AsyncMock, side_effect=RuntimeError("fail")):
        cmd = SlashCommand(name="model", args="x/y", raw="/model x/y")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "restart failed" in result.message


@pytest.mark.asyncio
async def test_model_set_pi_restart_not_ok(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_model", None)
    with patch("vibes.pi_client.stop_pi_agent", new_callable=AsyncMock), \
         patch("vibes.pi_client.start_pi_agent", new_callable=AsyncMock, return_value=False):
        cmd = SlashCommand(name="model", args="x/y", raw="/model x/y")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "restart failed" in result.message


@pytest.mark.asyncio
async def test_thinking_set_pi_restart_exception(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_thinking", None)
    with patch("vibes.pi_client.stop_pi_agent", new_callable=AsyncMock, side_effect=RuntimeError("fail")):
        cmd = SlashCommand(name="thinking", args="high", raw="/thinking high")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "restart failed" in result.message


@pytest.mark.asyncio
async def test_thinking_set_pi_restart_not_ok(monkeypatch):
    config = importlib.import_module("vibes.config").get_config()
    monkeypatch.setattr(config, "pi_thinking", None)
    with patch("vibes.pi_client.stop_pi_agent", new_callable=AsyncMock), \
         patch("vibes.pi_client.start_pi_agent", new_callable=AsyncMock, return_value=False):
        cmd = SlashCommand(name="thinking", args="medium", raw="/thinking medium")
        result = await execute_command(cmd, "pi")
        assert result.status == "error"
        assert "restart failed" in result.message


@pytest.mark.asyncio
async def test_shell_generic_exception(monkeypatch):
    import asyncio as _asyncio

    async def _boom(*a, **kw):
        raise OSError("no such file")

    monkeypatch.setattr(_asyncio, "create_subprocess_shell", _boom)
    cmd = SlashCommand(name="shell", args="echo hi", raw="/shell echo hi")
    result = await execute_command(cmd, "acp")
    assert result.status == "error"
    assert "Shell error" in result.message
