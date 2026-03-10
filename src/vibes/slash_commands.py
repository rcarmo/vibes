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
    refresh_agents: bool = False  # True to tell frontend to reload agents
    model_label: Optional[str] = None
    thinking_level: Optional[str] = None
    supports_thinking: Optional[bool] = None


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

    if command.name == "abort":
        return await _handle_abort(agent_mode)

    if command.name == "queue":
        return await _handle_queue(command.args, agent_mode)

    if command.name == "prompt":
        return _handle_prompt(command.args)

    if command.name == "name" or command.name == "agent-name":
        return _handle_agent_name(command.args)

    if command.name == "agent-avatar":
        return await _handle_agent_avatar(command.args)

    if command.name == "user-name":
        return _handle_user_name(command.args)

    if command.name == "user-avatar":
        return await _handle_user_avatar(command.args)

    if command.name == "user-github":
        return await _handle_user_github(command.args)

    if command.name == "theme":
        return await _handle_theme(command.args)

    if command.name == "tint":
        return await _handle_tint(command.args)

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
        "- `/prompt [text]` - Show or set the user system prompt",
        "- `/name [name]` - Show or set the agent display name",
        "- `/agent-name [name]` - Show or set the agent display name",
        "- `/agent-avatar [url|clear]` - Show or set the agent avatar URL",
        "- `/user-name [name|clear]` - Show or set your display name",
        "- `/user-avatar [url|clear]` - Show or set your avatar URL",
        "- `/user-github <username>` - Set name/avatar from GitHub profile",
        "- `/theme [name]` - Show or set the UI theme",
        "- `/tint [color|clear]` - Set or clear a UI colour tint",
        "- `/queue <message>` - Queue a message for after the current turn",
        "- `/abort` - Cancel the current agent operation",
        "- `/restart` - Restart the active agent",
        "- `/shell <command>` - Run a shell command",
        "- `/commands` - List available commands",
        "",
        "Messages sent while the agent is working are automatically sent as steering.",
        "Any other /command is forwarded to the agent.",
    ]
    return SlashCommandResult(status="success", message="\n".join(lines))


async def _restart_agent(agent_mode: str) -> SlashCommandResult:
    """Restart the active agent."""
    try:
        if agent_mode == "pi":
            from .pi_client import (
                send_rpc_command, is_pi_running, stop_pi_agent,
                start_pi_agent, cancel_current_request,
            )

            # Cancel any in-flight request so the lock is released.
            cancel_current_request()

            # Try RPC new_session first (keeps process alive).
            if is_pi_running():
                try:
                    resp = await send_rpc_command({"type": "new_session"})
                    if resp and resp.get("success"):
                        return SlashCommandResult(
                            status="success",
                            message="Pi agent session reset.",
                        )
                except Exception:
                    pass  # Fall through to hard restart.

            # Hard restart as fallback.
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
        return await _show_pi_model_info(config)

    # Set model via RPC (no restart needed).
    model_str = args.strip()
    # Parse "provider/model" format.
    if "/" in model_str:
        provider, model_id = model_str.split("/", 1)
    else:
        provider = ""
        model_id = model_str

    from .pi_client import send_rpc_command, is_pi_running

    if not is_pi_running():
        return SlashCommandResult(status="error", message="Pi agent is not running.")

    try:
        resp = await send_rpc_command({
            "type": "set_model",
            "provider": provider,
            "modelId": model_id,
        })
        if resp and resp.get("success"):
            model_data = resp.get("data", {})
            resolved = None
            if isinstance(model_data, dict):
                response_provider = str(model_data.get("provider", "") or "").strip()
                response_model_id = str(model_data.get("modelId") or model_data.get("id") or "").strip()
                if response_model_id:
                    resolved = (
                        f"{response_provider}/{response_model_id}"
                        if response_provider
                        else response_model_id
                    )
            if not resolved:
                resolved = f"{provider}/{model_id}" if provider else model_id
            config.pi_model = resolved
            from .config import save_setting
            save_setting("pi_model", resolved)

            # Query current state for thinking support info
            thinking_level = config.pi_thinking or None
            supports_thinking = None
            try:
                state_resp = await send_rpc_command({"type": "get_state"}, timeout=2.0)
                if state_resp and state_resp.get("success"):
                    state_data = state_resp.get("data", {})
                    tl = state_data.get("thinkingLevel")
                    if tl:
                        thinking_level = tl
                    st = state_data.get("supportsThinking")
                    if st is not None:
                        supports_thinking = bool(st)
            except Exception:
                pass

            thinking_note = f" Thinking level: {thinking_level}." if thinking_level else ""
            return SlashCommandResult(
                status="success",
                message=f"Model set to `{resolved}`.{thinking_note}",
                model_label=resolved,
                thinking_level=thinking_level,
                supports_thinking=supports_thinking,
            )
        error = resp.get("error", "Unknown error") if resp else "No response"
        return SlashCommandResult(status="error", message=f"Failed to set model: {error}")
    except Exception as e:
        return SlashCommandResult(status="error", message=f"Failed to set model: {e}")


async def _show_pi_model_info(config) -> SlashCommandResult:
    """Show current model and list available models via RPC."""
    from .pi_client import send_rpc_command, is_pi_running

    current = config.pi_model or "(default — pi selects automatically)"
    thinking = config.pi_thinking or "off"
    lines = [f"Current model: {current}", f"Thinking level: {thinking}"]

    # Try to get state from Pi for accurate current model.
    if is_pi_running():
        try:
            state_resp = await send_rpc_command({"type": "get_state"})
            if state_resp and state_resp.get("success"):
                data = state_resp.get("data", {})
                model = data.get("model")
                if isinstance(model, dict):
                    current_model = _format_model_identifier(model)
                    if current_model:
                        lines[0] = f"Current model: {current_model}"
                tl = data.get("thinkingLevel", "off")
                lines[1] = f"Thinking level: {tl}"
        except Exception:
            pass

    # Get available models via RPC.
    models_list = await _query_pi_models_rpc()
    if not models_list:
        models_list = await _query_pi_models_cli(config)

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


async def _query_pi_models_rpc() -> list[str]:
    """Get available models via the RPC get_available_models command."""
    from .pi_client import send_rpc_command, is_pi_running

    if not is_pi_running():
        return []
    try:
        resp = await send_rpc_command({"type": "get_available_models"})
        if not resp or not resp.get("success"):
            return []
        data = resp.get("data", {})
        raw_models = data.get("models", [])
        models = []
        for m in raw_models:
            if isinstance(m, dict):
                name = _format_model_identifier(m)
                if name:
                    models.append(name)
        return sorted(models)
    except Exception:
        logger.debug("Failed to query models via RPC", exc_info=True)
        return []


def _format_model_identifier(model: dict) -> str:
    provider = str(model.get("provider", "") or "").strip()
    model_id = str(model.get("modelId") or model.get("id") or model.get("name") or "").strip()
    if provider and model_id:
        return f"{provider}/{model_id}"
    return model_id


async def _query_pi_models_cli(config) -> list[str]:
    """Fallback: get available models from the pi CLI."""
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
        models = []
        for line in output.strip().splitlines()[1:]:
            cols = line.split()
            if len(cols) >= 2:
                models.append(f"{cols[0]}/{cols[1]}")
        return sorted(models)
    except Exception:
        logger.debug("Failed to query pi models via CLI", exc_info=True)
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

    # Set via RPC (no restart needed).
    from .pi_client import send_rpc_command, is_pi_running

    if not is_pi_running():
        return SlashCommandResult(status="error", message="Pi agent is not running.")

    try:
        resp = await send_rpc_command({"type": "set_thinking_level", "level": level})
        if resp and resp.get("success"):
            config.pi_thinking = level if level != "off" else None
            from .config import save_setting
            save_setting("pi_thinking", config.pi_thinking)
            return SlashCommandResult(
                status="success",
                message=f"Thinking level set to `{level}`.",
                model_label=config.pi_model or None,
                thinking_level=level,
                supports_thinking=True,
            )
        error = resp.get("error", "Unknown error") if resp else "No response"
        return SlashCommandResult(status="error", message=f"Failed to set thinking level: {error}")
    except Exception as e:
        return SlashCommandResult(status="error", message=f"Failed to set thinking level: {e}")


async def _handle_abort(agent_mode: str) -> SlashCommandResult:
    """Abort the current agent operation."""
    if agent_mode != "pi":
        return SlashCommandResult(
            status="error",
            message="Abort is only supported for Pi agents.",
        )

    from .pi_client import send_rpc_fire_and_forget, cancel_current_request

    # Send abort to Pi and cancel the in-flight event loop task.
    ok = await send_rpc_fire_and_forget({"type": "abort"})
    cancelled = cancel_current_request()
    if ok or cancelled:
        return SlashCommandResult(status="success", message="Abort signal sent.")
    return SlashCommandResult(status="error", message="Pi agent is not running.")


async def _handle_queue(args: str, agent_mode: str) -> SlashCommandResult:
    """Queue a message to be sent after the current turn completes."""
    if not args:
        return SlashCommandResult(
            status="error",
            message="Usage: `/queue <message>`",
        )

    if agent_mode != "pi":
        return SlashCommandResult(
            status="error",
            message="Message queueing is only supported for Pi agents.",
        )

    from .pi_client import is_busy, queue_message

    if not is_busy():
        return SlashCommandResult(
            status="success",
            message="Agent is idle — send your message directly (no need to queue).",
        )

    queue_message(args)
    return SlashCommandResult(
        status="success",
        message=f"Message queued — will be sent after the current turn:\n```\n{args}\n```",
    )


def _handle_prompt(args: str) -> SlashCommandResult:
    """Show or set the user system prompt.

    With no args, displays the current prompt.
    With args, sets the prompt (takes effect on next agent restart).
    Use `/prompt clear` to remove the prompt.
    """
    from .config import get_config

    config = get_config()

    if not args:
        if config.prompt:
            return SlashCommandResult(
                status="success",
                message=f"Current prompt:\n```\n{config.prompt}\n```",
            )
        return SlashCommandResult(
            status="success",
            message="No user prompt set. Use `/prompt <text>` to set one.",
        )

    if args.strip().lower() == "clear":
        config.prompt = ""
        from .config import save_setting
        save_setting("prompt", None)
        return SlashCommandResult(
            status="success",
            message="User prompt cleared. Restart the agent for changes to take effect.",
        )

    config.prompt = args
    from .config import save_setting
    save_setting("prompt", args)
    return SlashCommandResult(
        status="success",
        message=f"User prompt set. Restart the agent for changes to take effect.\n```\n{args}\n```",
    )


def _handle_agent_name(args: str) -> SlashCommandResult:
    """Show or set the agent display name."""
    from .config import get_config

    config = get_config()

    if not args:
        return SlashCommandResult(
            status="success",
            message=f"Agent name: **{config.agent_name}**",
        )

    if args.strip().lower() == "clear":
        import socket
        config.agent_name = socket.gethostname()
        from .config import save_setting
        save_setting("agent_name", None)
        return SlashCommandResult(
            status="success",
            message=f"Agent name reset to default: **{config.agent_name}**",
            refresh_agents=True,
        )

    config.agent_name = args.strip()
    from .config import save_setting
    save_setting("agent_name", args.strip())
    return SlashCommandResult(
        status="success",
        message=f"Agent name set to **{args.strip()}**",
        refresh_agents=True,
    )


async def _handle_agent_avatar(args: str) -> SlashCommandResult:
    """Show or set the agent avatar URL."""
    from .avatar import clear_avatar_cache, ensure_avatar_cache
    from .config import get_config

    config = get_config()

    if not args:
        if config.agent_avatar:
            return SlashCommandResult(
                status="success",
                message=f"Agent avatar: {config.agent_avatar}",
            )
        return SlashCommandResult(
            status="success",
            message="No agent avatar set. Use `/agent-avatar <url>` to set one.",
        )

    if args.strip().lower() == "clear":
        config.agent_avatar = ""
        from .config import save_setting
        save_setting("agent_avatar", None)
        clear_avatar_cache("agent")
        return SlashCommandResult(
            status="success",
            message="Agent avatar cleared.",
            refresh_agents=True,
        )

    url = args.strip()
    config.agent_avatar = url
    from .config import save_setting
    save_setting("agent_avatar", url)

    meta = await ensure_avatar_cache("agent", url)
    if meta:
        return SlashCommandResult(
            status="success",
            message=f"Agent avatar set and cached from {url}",
            refresh_agents=True,
        )
    return SlashCommandResult(
        status="success",
        message=f"Agent avatar set to {url} (could not cache — will use URL directly)",
        refresh_agents=True,
    )


def _handle_user_name(args: str) -> SlashCommandResult:
    """Show or set the user display name."""
    from .config import get_config

    config = get_config()

    if not args:
        name = config.user_name or "(not set — defaults to 'You')"
        return SlashCommandResult(
            status="success",
            message=f"User name: **{name}**",
        )

    if args.strip().lower() == "clear":
        config.user_name = ""
        from .config import save_setting
        save_setting("user_name", None)
        return SlashCommandResult(
            status="success",
            message="User name cleared (will show as 'You').",
            refresh_agents=True,
        )

    config.user_name = args.strip()
    from .config import save_setting
    save_setting("user_name", args.strip())
    return SlashCommandResult(
        status="success",
        message=f"User name set to **{args.strip()}**",
        refresh_agents=True,
    )


async def _handle_user_avatar(args: str) -> SlashCommandResult:
    """Show or set the user avatar URL."""
    from .avatar import clear_avatar_cache, ensure_avatar_cache
    from .config import get_config

    config = get_config()

    if not args:
        if config.user_avatar:
            return SlashCommandResult(
                status="success",
                message=f"User avatar: {config.user_avatar}",
            )
        return SlashCommandResult(
            status="success",
            message="No user avatar set. Use `/user-avatar <url>` to set one.",
        )

    if args.strip().lower() == "clear":
        config.user_avatar = ""
        config.user_avatar_background = ""
        from .config import save_setting
        save_setting("user_avatar", None)
        save_setting("user_avatar_background", None)
        clear_avatar_cache("user")
        return SlashCommandResult(
            status="success",
            message="User avatar cleared.",
            refresh_agents=True,
        )

    url = args.strip()
    config.user_avatar = url
    from .config import save_setting
    save_setting("user_avatar", url)

    meta = await ensure_avatar_cache("user", url)
    if meta:
        return SlashCommandResult(
            status="success",
            message=f"User avatar set and cached from {url}",
            refresh_agents=True,
        )
    return SlashCommandResult(
        status="success",
        message=f"User avatar set to {url} (could not cache — will use URL directly)",
        refresh_agents=True,
    )


async def _handle_user_github(args: str) -> SlashCommandResult:
    """Set user name and avatar from a GitHub profile."""
    import json
    import urllib.request

    if not args:
        return SlashCommandResult(
            status="error",
            message="Usage: `/user-github <username>`",
        )

    username = args.strip().lstrip("@")
    # Accept full GitHub URLs like https://github.com/rcarmo
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if username.lower().startswith(prefix):
            username = username[len(prefix):].strip("/").split("/")[0]
            break
    url = f"https://api.github.com/users/{username}"

    try:
        loop = asyncio.get_event_loop()
        req = urllib.request.Request(url, headers={"User-Agent": "vibes"})
        resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=10))
        data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return SlashCommandResult(
            status="error",
            message=f"Failed to fetch GitHub profile for `{username}`: {e}",
        )

    gh_name = data.get("name") or username
    gh_avatar = data.get("avatar_url") or ""

    from .avatar import ensure_avatar_cache
    from .config import get_config, save_setting

    config = get_config()
    config.user_name = gh_name
    config.user_avatar = gh_avatar
    config.user_avatar_background = "transparent"
    save_setting("user_name", gh_name)
    save_setting("user_avatar", gh_avatar)
    save_setting("user_avatar_background", "transparent")

    if gh_avatar:
        await ensure_avatar_cache("user", gh_avatar)

    return SlashCommandResult(
        status="success",
        message=f"User profile set from GitHub:\n- Name: **{gh_name}**\n- Avatar: {gh_avatar}",
        refresh_agents=True,
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


AVAILABLE_THEMES = [
    "default", "monokai", "monokai-pro", "dracula", "catppuccin",
    "nord", "gruvbox", "solarized", "tokyo", "miasma",
    "github", "gotham", "tango", "xterm", "ristretto",
]


async def _handle_theme(args: str) -> SlashCommandResult:
    """Show or set the UI theme."""
    from .routes.sse import broadcast_event

    if not args:
        return SlashCommandResult(
            status="success",
            message="Available themes: " + ", ".join(f"`{t}`" for t in AVAILABLE_THEMES)
            + "\n\nSet with: `/theme <name>`",
        )

    name = args.strip().lower()
    if name not in AVAILABLE_THEMES:
        return SlashCommandResult(
            status="error",
            message=f"Unknown theme `{name}`. Available: {', '.join(AVAILABLE_THEMES)}",
        )

    await broadcast_event("ui_theme", {"theme": name})
    return SlashCommandResult(
        status="success",
        message=f"Theme set to `{name}`.",
    )


async def _handle_tint(args: str) -> SlashCommandResult:
    """Set or clear a UI colour tint."""
    from .routes.sse import broadcast_event

    if not args or args.strip().lower() == "clear":
        await broadcast_event("ui_theme", {"tint": None})
        return SlashCommandResult(
            status="success",
            message="UI tint cleared.",
        )

    color = args.strip()
    await broadcast_event("ui_theme", {"tint": color})
    return SlashCommandResult(
        status="success",
        message=f"UI tint set to `{color}`.",
    )
