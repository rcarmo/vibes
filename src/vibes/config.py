"""Configuration loader for Vibes."""

import json
import os
import socket
from pathlib import Path
from typing import Optional

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


class Config:
    """Application configuration."""

    def __init__(self):
        self.host: str = _get_env("VIBES_HOST", "0.0.0.0")
        self.port: int = _get_env_int("VIBES_PORT", 8080)
        self.db_path: str = _get_env("VIBES_DB_PATH", "data/app.db")
        self.debug: bool = _get_env_bool("VIBES_DEBUG", False)
        self.custom_endpoints: dict = {}
        
        # ACP agent configuration
        self.acp_agent: str = _get_env("VIBES_ACP_AGENT", "vibe-acp")
        self.agent_name: str = _get_env("VIBES_AGENT_NAME", socket.gethostname())
        self.permission_request_timeout_s: int = _get_env_int("VIBES_PERMISSION_TIMEOUT_S", 30)
        
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


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
