"""Slash command parser and executor for Vibes.

Ported from piclaw's agent-control.ts — intercepts messages starting with '/'
and dispatches built-in control commands or forwards to the active agent.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

SHELL_TIMEOUT = 30

THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh")


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

    if command.name == "model":
        return await _handle_model(command.args, agent_mode)

    if command.name == "thinking":
        return await _handle_thinking(command.args, agent_mode)

    if command.name == "shell":
        return await _run_shell(command.args)

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
        "- `/model [provider/model]` - Show or set the model",
        "- `/thinking [level]` - Show or set thinking level",
        "- `/restart` - Restart the active agent",
        "- `/shell <command>` - Run a shell command",
        "- `/commands` - List available commands",
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


async def _handle_model(args: str, agent_mode: str) -> SlashCommandResult:
    """Show or set the model for the active agent."""
    from .config import get_config

    config = get_config()

    if agent_mode != "pi":
        current = config.acp_agent
        if not args:
            return SlashCommandResult(
                status="success",
                message=f"Current ACP agent: `{current}`.\n\n"
                "Model selection requires restarting with a different ACP agent binary.",
            )
        return SlashCommandResult(
            status="error",
            message="Model selection is not supported for ACP agents. "
            "Set `VIBES_ACP_AGENT` and restart.",
        )

    # Pi mode — list models
    if not args:
        current = config.pi_model or "(default — pi selects automatically)"
        thinking = config.pi_thinking or "off"
        models_list = await _query_pi_models(config)
        lines = [f"Current model: {current}", f"Thinking level: {thinking}"]
        if models_list:
            lines.append("")
            lines.append("Available models:")
            lines.append("")
            for name in models_list:
                if name == config.pi_model:
                    lines.append(f"- `{name}` *(current)*")
                else:
                    lines.append(f"- `{name}`")
        lines.append("")
        lines.append("Set with: `/model <provider/model>`")
        return SlashCommandResult(status="success", message="\n".join(lines))

    # Set model and restart
    config.pi_model = args.strip()
    try:
        from .pi_client import stop_pi_agent, start_pi_agent
        await stop_pi_agent()
        ok = await start_pi_agent()
    except Exception as e:
        logger.error(f"Error restarting Pi agent after model change: {e}", exc_info=True)
        return SlashCommandResult(status="error", message=f"Model set but restart failed: {e}")

    if not ok:
        return SlashCommandResult(status="error", message=f"Model set to {config.pi_model} but restart failed.")

    thinking_note = f" Thinking level: {config.pi_thinking}." if config.pi_thinking else ""
    return SlashCommandResult(
        status="success",
        message=f"Model set to {config.pi_model}. Pi agent restarted.{thinking_note}",
    )


async def _query_pi_models(config) -> list[str]:
    """Try to get available models from the pi CLI."""
    import shlex
    import shutil

    cmd_parts = shlex.split(config.pi_agent)
    if not cmd_parts:
        return []
    executable = cmd_parts[0]
    if not shutil.which(executable):
        return []

    try:
        proc = await asyncio.create_subprocess_exec(
            executable, "--list-models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            stdin=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        if proc.returncode != 0 or not output.strip():
            return []
        # Parse tabular output: "provider  model  context  ..."
        # Skip header line, build provider/model identifiers
        models = []
        for line in output.strip().splitlines()[1:]:
            cols = line.split()
            if len(cols) >= 2:
                models.append(f"{cols[0]}/{cols[1]}")
        return sorted(models)
    except Exception:
        logger.debug("Failed to query pi models", exc_info=True)
        return []


async def _handle_thinking(args: str, agent_mode: str) -> SlashCommandResult:
    """Show or set the thinking level for the active agent."""
    from .config import get_config

    config = get_config()

    if agent_mode != "pi":
        return SlashCommandResult(
            status="error",
            message="Thinking level configuration is not supported for ACP agents.",
        )

    # Pi mode — show current
    if not args:
        current = config.pi_thinking or "off"
        model = config.pi_model or "(default)"
        return SlashCommandResult(
            status="success",
            message=f"Current model: {model}\n"
            f"Current thinking level: {current}\n"
            f"Available levels: {', '.join(THINKING_LEVELS)}",
        )

    # Validate level
    level = args.strip().lower()
    if level not in THINKING_LEVELS:
        return SlashCommandResult(
            status="error",
            message=f"Unknown thinking level: {args}. Available: {', '.join(THINKING_LEVELS)}",
        )

    config.pi_thinking = level if level != "off" else None
    try:
        from .pi_client import stop_pi_agent, start_pi_agent
        await stop_pi_agent()
        ok = await start_pi_agent()
    except Exception as e:
        logger.error(f"Error restarting Pi agent after thinking change: {e}", exc_info=True)
        return SlashCommandResult(status="error", message=f"Thinking level set but restart failed: {e}")

    if not ok:
        return SlashCommandResult(status="error", message=f"Thinking set to {level} but restart failed.")

    effective = config.pi_thinking or "off"
    return SlashCommandResult(
        status="success",
        message=f"Thinking level set to {effective}. Pi agent restarted.",
    )


async def _run_shell(args: str) -> SlashCommandResult:
    """Run a shell command and return stdout/stderr as a fenced code block."""
    if not args:
        return SlashCommandResult(
            status="error",
            message="Usage: `/shell <command>`",
        )

    try:
        proc = await asyncio.create_subprocess_shell(
            args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=SHELL_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return SlashCommandResult(
                status="error",
                message=f"$ {args}\n```\n[timed out after {SHELL_TIMEOUT}s]\n```",
            )
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        exit_label = f"exit code {proc.returncode}" if proc.returncode else "ok"
        header = f"$ {args}  [{exit_label}]"
        message = f"{header}\n```\n{output}```"
        return SlashCommandResult(
            status="success" if proc.returncode == 0 else "error",
            message=message,
        )
    except Exception as e:
        logger.error(f"Shell command error: {e}", exc_info=True)
        return SlashCommandResult(
            status="error",
            message=f"Shell error: {e}",
        )
