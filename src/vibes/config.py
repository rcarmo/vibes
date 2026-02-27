"""Configuration loader for Vibes."""

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
ENV_BOOL_TRUE = {"1", "true", "yes"}


def _get_env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _get_env_int(key: str, default: int) -> int:
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.lower() in ENV_BOOL_TRUE


def _default_pi_agent_command() -> str:
    extension_path = Path(__file__).parent / "extensions" / "pi-vibes-tools.ts"
    quoted_extension = shlex.quote(str(extension_path))
    quoted_prompt = shlex.quote(PI_PROMPT_PREFIX)
    return (
        "pi --mode rpc --no-session "
        f"--append-system-prompt {quoted_prompt} "
        f"-e {quoted_extension}"
    )


class Config:
    """Application configuration."""

    def __init__(self):
        self.host: str = _get_env("VIBES_HOST", "0.0.0.0")
        self.port: int = _get_env_int("VIBES_PORT", 8080)
        self.db_path: str = _get_env("VIBES_DB_PATH", "database/vibes.db")
        self.debug: bool = _get_env_bool("VIBES_DEBUG", False)
        self.custom_endpoints: dict = {}
        
        # ACP agent configuration
        self.acp_agent: str = _get_env("VIBES_ACP_AGENT", "vibe-acp")
        self.agent_name: str = _get_env("VIBES_AGENT_NAME", socket.gethostname())
        self.permission_timeout: int = _get_env_int("VIBES_PERMISSION_TIMEOUT", 30)
        self.permission_auto_approve: bool = _get_env_bool("VIBES_PERMISSION_AUTO_APPROVE", False)
        self.disconnect_timeout: int = _get_env_int("VIBES_DISCONNECT_TIMEOUT", 300)
        self.acp_debug: bool = _get_env_bool("VIBES_ACP_DEBUG", False)
        self.acp_throttle_rps: int = _get_env_int("VIBES_ACP_THROTTLE_RPS", 0)

        # Pi agent configuration (RPC mode)
        self.default_agent: str = _get_env("VIBES_DEFAULT_AGENT", "acp")
        self.pi_agent: str = _get_env(
            "VIBES_PI_AGENT",
            _default_pi_agent_command(),
        )
        self.pi_enabled: bool = _get_env_bool(
            "VIBES_PI_ENABLED",
            self.default_agent.lower() == "pi"
        )
        self.pi_restart_on_disconnect: bool = _get_env_bool(
            "VIBES_PI_RESTART_ON_DISCONNECT",
            False,
        )
        # Pi RPC idle timeouts (seconds). Set to 0 to disable timeout.
        self.pi_response_timeout_s: int = _get_env_int("VIBES_PI_RESPONSE_TIMEOUT_S", 0)
        self.pi_agent_end_timeout_s: int = _get_env_int("VIBES_PI_AGENT_END_TIMEOUT_S", 0)

        # Runtime-mutable overrides for Pi model and thinking level.
        # Applied via CLI flags on initial startup; changed live via RPC set_model/set_thinking_level.
        self.pi_model: Optional[str] = os.environ.get("VIBES_PI_MODEL")
        self.pi_thinking: Optional[str] = os.environ.get("VIBES_PI_THINKING")
        
        # Load custom endpoints from config file
        config_path = _get_env("VIBES_CONFIG_PATH", DEFAULT_CONFIG_PATH)
        if Path(config_path).exists():
            self._load_custom_endpoints(config_path)

    def _load_custom_endpoints(self, config_path: str) -> None:
        """Load custom endpoint definitions from JSON file."""
        try:
            with open(config_path) as f:
                data = json.load(f)
                self.custom_endpoints = data.get("endpoints", {})
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load config from {config_path}: {e}")

    def effective_pi_command(self) -> str:
        """Return the pi agent command with model/thinking overrides appended."""
        cmd = self.pi_agent
        if self.pi_model:
            cmd += f" --model {shlex.quote(self.pi_model)}"
        if self.pi_thinking:
            cmd += f" --thinking {shlex.quote(self.pi_thinking)}"
        return cmd


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
