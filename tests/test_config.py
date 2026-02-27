import json
import shlex
import sys
import importlib
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) in sys.path:
    sys.path.remove(str(SRC_PATH))
sys.path.insert(0, str(SRC_PATH))

for module_name in list(sys.modules.keys()):
    if module_name == "vibes" or module_name.startswith("vibes."):
        sys.modules.pop(module_name, None)

config_mod = importlib.import_module("vibes.config")
_default_pi_agent_command = config_mod._default_pi_agent_command
_find_settings_file = config_mod._find_settings_file
_load_settings_file = config_mod._load_settings_file
_resolve = config_mod._resolve
PI_PROMPT_PREFIX = importlib.import_module("vibes.pi_prompt").PI_PROMPT_PREFIX
Config = config_mod.Config


def test_default_pi_agent_command_includes_prompt_and_extension():
    cmd = _default_pi_agent_command()
    assert "--append-system-prompt" in cmd
    assert "pi-vibes-tools.ts" in cmd
    assert shlex.quote(PI_PROMPT_PREFIX) in cmd
    ext_path = Path(__file__).resolve().parents[1] / "src" / "vibes" / "extensions" / "pi-vibes-tools.ts"
    assert str(ext_path) in cmd


def test_effective_pi_command_no_overrides():
    config = Config()
    config.pi_model = None
    config.pi_thinking = None
    assert config.effective_pi_command() == config.pi_agent


def test_effective_pi_command_with_model():
    config = Config()
    config.pi_model = "anthropic/claude-sonnet"
    config.pi_thinking = None
    cmd = config.effective_pi_command()
    assert "--model" in cmd
    assert "anthropic/claude-sonnet" in cmd


def test_effective_pi_command_with_thinking():
    config = Config()
    config.pi_model = None
    config.pi_thinking = "high"
    cmd = config.effective_pi_command()
    assert "--thinking" in cmd
    assert "high" in cmd


def test_effective_pi_command_with_both():
    config = Config()
    config.pi_model = "openai/gpt-4"
    config.pi_thinking = "medium"
    cmd = config.effective_pi_command()
    assert "--model" in cmd
    assert "openai/gpt-4" in cmd
    assert "--thinking" in cmd
    assert "medium" in cmd


# --- Settings file tests ---

def test_find_settings_file_in_cwd(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    settings_file.write_text('{"port": 9999}')
    monkeypatch.chdir(tmp_path)
    result = _find_settings_file()
    assert result is not None
    assert result.name == "settings.json"


def test_find_settings_file_xdg_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no .vibes/ here
    xdg_dir = tmp_path / "xdg_config" / "vibes"
    xdg_dir.mkdir(parents=True)
    (xdg_dir / "settings.json").write_text('{"port": 8888}')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    result = _find_settings_file()
    assert result is not None
    assert str(result).endswith("settings.json")


def test_find_settings_file_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
    assert _find_settings_file() is None


def test_resolve_env_wins_over_file():
    settings = {"port": 9999}
    import os
    old = os.environ.get("VIBES_PORT")
    try:
        os.environ["VIBES_PORT"] = "7777"
        assert _resolve(settings, "port", "VIBES_PORT", 8080, "int") == 7777
    finally:
        if old is None:
            os.environ.pop("VIBES_PORT", None)
        else:
            os.environ["VIBES_PORT"] = old


def test_resolve_file_value_used():
    settings = {"port": 9999}
    import os
    old = os.environ.pop("VIBES_PORT", None)
    try:
        assert _resolve(settings, "port", "VIBES_PORT", 8080, "int") == 9999
    finally:
        if old is not None:
            os.environ["VIBES_PORT"] = old


def test_resolve_default_when_neither():
    import os
    old = os.environ.pop("VIBES_PORT", None)
    try:
        assert _resolve({}, "port", "VIBES_PORT", 8080, "int") == 8080
    finally:
        if old is not None:
            os.environ["VIBES_PORT"] = old


def test_resolve_bool_from_file():
    assert _resolve({"debug": True}, "debug", "VIBES_DEBUG", False, "bool") is True
    assert _resolve({"debug": "yes"}, "debug", "VIBES_DEBUG", False, "bool") is True
    assert _resolve({"debug": "false"}, "debug", "VIBES_DEBUG", False, "bool") is False


def test_config_loads_settings_file(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(json.dumps({
        "port": 3000,
        "debug": True,
        "pi_model": "test-model",
    }))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIBES_PORT", raising=False)
    monkeypatch.delenv("VIBES_DEBUG", raising=False)
    monkeypatch.delenv("VIBES_PI_MODEL", raising=False)
    config = Config()
    assert config.port == 3000
    assert config.debug is True
    assert config.pi_model == "test-model"
    assert config.settings_file is not None


def test_config_inline_endpoints(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(json.dumps({
        "endpoints": {
            "my_tool": {"agent_id": "default", "description": "test"}
        }
    }))
    monkeypatch.chdir(tmp_path)
    config = Config()
    assert "my_tool" in config.custom_endpoints
