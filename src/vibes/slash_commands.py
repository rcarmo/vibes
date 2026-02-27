"""Slash command parser and executor for Vibes.

Ported from piclaw's agent-control.ts — intercepts messages starting with '/'
and dispatches built-in control commands or forwards to the active agent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SlashCommandResult:
    """Result of executing a slash command."""
    status: str  # "success" or "error"
    message: str
    handled: bool = True  # False means forward to agent as normal prompt


@dataclass
class SlashCommand:
    """Parsed slash command."""
    name: str
    args: str = ""
    raw: str = ""


def parse_command(text: str) -> Optional[SlashCommand]:
    """Parse a slash command from message text.

    Returns None if the text is not a slash command.
    """
    if not text:
        return None
    trimmed = text.strip()
    if not trimmed.startswith("/"):
        return None

    parts = trimmed.split(None, 1)
    name = parts[0][1:].lower()  # strip leading '/'
    args = parts[1].strip() if len(parts) > 1 else ""
    return SlashCommand(name=name, args=args, raw=trimmed)


async def execute_command(
    command: SlashCommand,
    agent_mode: str,
) -> SlashCommandResult:
    """Execute a parsed slash command.

    Built-in commands are handled directly.
    Unknown commands return handled=False so the caller can forward to the agent.
    """
    if command.name == "commands":
        return _list_commands()

    if command.name == "restart":
        return await _restart_agent(agent_mode)

    # Unknown command — tell caller to forward to agent
    return SlashCommandResult(
        status="success",
        message="",
        handled=False,
    )


def _list_commands() -> SlashCommandResult:
    """List available slash commands."""
    lines = [
        "Available commands:",
        "• /restart — Restart the active agent",
        "• /commands — List available commands",
        "",
        "Any other /command is forwarded to the agent.",
    ]
    return SlashCommandResult(status="success", message="\n".join(lines))


async def _restart_agent(agent_mode: str) -> SlashCommandResult:
    """Restart the active agent (stop + start)."""
    try:
        if agent_mode == "pi":
            from .pi_client import stop_pi_agent, start_pi_agent
            await stop_pi_agent()
            ok = await start_pi_agent()
            label = "Pi agent"
        else:
            from .acp_client import stop_agent, start_agent
            await stop_agent()
            ok = await start_agent()
            label = "ACP agent"

        if ok:
            return SlashCommandResult(
                status="success",
                message=f"{label} restarted.",
            )
        return SlashCommandResult(
            status="error",
            message=f"Failed to restart {label}.",
        )
    except Exception as e:
        logger.error(f"Error restarting agent: {e}", exc_info=True)
        return SlashCommandResult(
            status="error",
            message=f"Restart failed: {e}",
        )
