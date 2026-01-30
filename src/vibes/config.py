"""Configuration loader for Vibes."""

import json
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

DEFAULT_CONFIG_PATH = "config/endpoints.json"


class Config:
    """Application configuration."""

    def __init__(self):
        self.host: str = os.environ.get("VIBES_HOST", "0.0.0.0")
        self.port: int = int(os.environ.get("VIBES_PORT", "8080"))
        self.db_path: str = os.environ.get("VIBES_DB_PATH", "data/app.db")
        self.debug: bool = os.environ.get("VIBES_DEBUG", "").lower() in ("1", "true", "yes")
        self.custom_endpoints: dict = {}
        
        # ACP agent configuration
        self.acp_agent: str = os.environ.get("VIBES_ACP_AGENT", "vibe-acp")
        
        # Load custom endpoints from config file
        config_path = os.environ.get("VIBES_CONFIG_PATH", DEFAULT_CONFIG_PATH)
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
