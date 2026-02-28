"""Configuration loader for Vibes.

Settings resolution order (highest priority wins):
1. Environment variables (VIBES_*)
2. Settings file (.vibes/settings.json in workspace root, or XDG fallback)
3. Hard-coded defaults
"""

import json
import os
import shlex
import socket
from pathlib import Path
from typing import Optional

from .pi_prompt import PI_PROMPT_PREFIX

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

DEFAULT_CONFIG_PATH = "config/endpoints.json"
SETTINGS_DIR = ".vibes"
SETTINGS_FILENAME = "settings.json"
ENV_BOOL_TRUE = {"1", "true", "yes"}


def _find_settings_file() -> Optional[Path]:
    """Locate settings.json: .vibes/ in cwd first, then XDG config fallback."""
    local = Path(SETTINGS_DIR) / SETTINGS_FILENAME
    if local.is_file():
        return local

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    xdg_dir = Path(xdg_config) if xdg_config else Path.home() / ".config"
    xdg_path = xdg_dir / "vibes" / SETTINGS_FILENAME
    if xdg_path.is_file():
        return xdg_path

    return None


def _settings_write_path() -> Path:
    """Return the path to write settings to (creates .vibes/ if needed)."""
    existing = _find_settings_file()
    if existing is not None:
        return existing
    # Default to .vibes/settings.json in cwd
    d = Path(SETTINGS_DIR)
    d.mkdir(exist_ok=True)
    return d / SETTINGS_FILENAME


def save_setting(key: str, value) -> None:
    """Persist a single setting to the settings file.

    Reads the current file, updates the key, and writes back.
    Creates .vibes/settings.json if it doesn't exist yet.
    """
    path = _settings_write_path()
    data: dict = {}
    if path.is_file():
        try:
            with open(path) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except (json.JSONDecodeError, IOError):
            data = {}
    if value is None or value == "":
        data.pop(key, None)
    else:
        data[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _load_settings_file() -> dict:
    """Load and return settings from the settings file, or empty dict."""
    path = _find_settings_file()
    if path is None:
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(f"Warning: {path} is not a JSON object, ignoring")
            return {}
        return data
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load settings from {path}: {e}")
        return {}


def _resolve(settings: dict, key: str, env_key: str, default, type_name: str):
    """Resolve a setting: env var > settings file > default."""
    env_val = os.environ.get(env_key)
    if env_val is not None:
        if type_name == "int":
            try:
                return int(env_val)
            except ValueError:
                return default
        elif type_name == "bool":
            return env_val.lower() in ENV_BOOL_TRUE
        return env_val

    if key in settings:
        file_val = settings[key]
        if type_name == "int":
            try:
                return int(file_val)
            except (ValueError, TypeError):
                return default
        elif type_name == "bool":
            if isinstance(file_val, bool):
                return file_val
            if isinstance(file_val, str):
                return file_val.lower() in ENV_BOOL_TRUE
            return default
        return str(file_val) if file_val is not None else default

    return default


def _default_pi_agent_command() -> str:
    extension_path = Path(__file__).parent / "extensions" / "pi-vibes-tools.ts"
    quoted_extension = shlex.quote(str(extension_path))
    return (
        "pi --mode rpc --no-session "
        f"-e {quoted_extension}"
    )


class Config:
    """Application configuration."""

    def __init__(self):
        s = _load_settings_file()

        self.host: str = _resolve(s, "host", "VIBES_HOST", "0.0.0.0", "str")
        self.port: int = _resolve(s, "port", "VIBES_PORT", 8080, "int")
        self.db_path: str = _resolve(s, "db_path", "VIBES_DB_PATH", "database/vibes.db", "str")
        self.debug: bool = _resolve(s, "debug", "VIBES_DEBUG", False, "bool")
        self.custom_endpoints: dict = {}
        
        # ACP agent configuration
        self.acp_agent: str = _resolve(s, "acp_agent", "VIBES_ACP_AGENT", "vibe-acp", "str")
        self.agent_name: str = _resolve(s, "agent_name", "VIBES_AGENT_NAME", socket.gethostname(), "str")
        self.permission_timeout: int = _resolve(s, "permission_timeout", "VIBES_PERMISSION_TIMEOUT", 30, "int")
        self.permission_auto_approve: bool = _resolve(s, "permission_auto_approve", "VIBES_PERMISSION_AUTO_APPROVE", False, "bool")
        self.disconnect_timeout: int = _resolve(s, "disconnect_timeout", "VIBES_DISCONNECT_TIMEOUT", 300, "int")
        self.acp_debug: bool = _resolve(s, "acp_debug", "VIBES_ACP_DEBUG", False, "bool")
        self.acp_throttle_rps: int = _resolve(s, "acp_throttle_rps", "VIBES_ACP_THROTTLE_RPS", 0, "int")

        # Pi agent configuration (RPC mode)
        self.default_agent: str = _resolve(s, "default_agent", "VIBES_DEFAULT_AGENT", "acp", "str")
        self.pi_agent: str = _resolve(
            s, "pi_agent", "VIBES_PI_AGENT",
            _default_pi_agent_command(), "str",
        )
        self.pi_enabled: bool = _resolve(
            s, "pi_enabled", "VIBES_PI_ENABLED",
            self.default_agent.lower() == "pi", "bool",
        )
        self.pi_restart_on_disconnect: bool = _resolve(
            s, "pi_restart_on_disconnect",
            "VIBES_PI_RESTART_ON_DISCONNECT", False, "bool",
        )
        # Pi RPC idle timeouts (seconds). These are per-event activity timeouts
        # that reset each time an event is received. Pi streams thinking_delta
        # events continuously while models think, so a timeout only fires when
        # Pi goes truly silent (e.g. API stall or process hang).
        # Set to 0 to disable timeout entirely.
        self.pi_response_timeout_s: int = _resolve(s, "pi_response_timeout_s", "VIBES_PI_RESPONSE_TIMEOUT_S", 120, "int")
        self.pi_agent_end_timeout_s: int = _resolve(s, "pi_agent_end_timeout_s", "VIBES_PI_AGENT_END_TIMEOUT_S", 30, "int")

        # Runtime-mutable overrides for Pi model and thinking level.
        # Applied via CLI flags on initial startup; changed live via RPC set_model/set_thinking_level.
        self.pi_model: Optional[str] = _resolve(s, "pi_model", "VIBES_PI_MODEL", None, "str")
        self.pi_thinking: Optional[str] = _resolve(s, "pi_thinking", "VIBES_PI_THINKING", None, "str")

        # User-supplied prompt appended to the system prompt for both Pi and ACP.
        # Can be changed at runtime via /prompt command.
        self.prompt: str = _resolve(s, "prompt", "VIBES_PROMPT", "", "str")
        
        # Load custom endpoints from config file
        config_path = _resolve(s, "config_path", "VIBES_CONFIG_PATH", DEFAULT_CONFIG_PATH, "str")
        if Path(config_path).exists():
            self._load_custom_endpoints(config_path)

        # Also load inline endpoints from settings file
        if "endpoints" in s and isinstance(s["endpoints"], dict):
            self.custom_endpoints.update(s["endpoints"])

        # Store which settings file was loaded (for diagnostics)
        self.settings_file: Optional[str] = str(_find_settings_file()) if _find_settings_file() else None

    def _load_custom_endpoints(self, config_path: str) -> None:
        """Load custom endpoint definitions from JSON file."""
        try:
            with open(config_path) as f:
                data = json.load(f)
                self.custom_endpoints = data.get("endpoints", {})
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load config from {config_path}: {e}")

    def effective_pi_command(self) -> str:
        """Return the pi agent command with model/thinking/prompt overrides appended."""
        cmd = self.pi_agent
        if self.pi_model:
            cmd += f" --model {shlex.quote(self.pi_model)}"
        if self.pi_thinking:
            cmd += f" --thinking {shlex.quote(self.pi_thinking)}"
        # Build combined system prompt: base + user prompt
        full_prompt = PI_PROMPT_PREFIX
        if self.prompt:
            full_prompt += "\n\n" + self.prompt
        cmd += f" --append-system-prompt {shlex.quote(full_prompt)}"
        return cmd


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
