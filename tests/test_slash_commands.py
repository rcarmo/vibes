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
