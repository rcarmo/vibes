import json
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
save_setting = config_mod.save_setting
PI_PROMPT_PREFIX = importlib.import_module("vibes.pi_prompt").PI_PROMPT_PREFIX
Config = config_mod.Config


def test_default_pi_agent_command_includes_prompt_and_extension():
    cmd = _default_pi_agent_command()
    assert "pi-vibes-tools.ts" in cmd
    ext_path = Path(__file__).resolve().parents[1] / "src" / "vibes" / "extensions" / "pi-vibes-tools.ts"
    assert str(ext_path) in cmd


def test_effective_pi_command_no_overrides():
    config = Config()
    config.pi_model = None
    config.pi_thinking = None
    config.prompt = ""
    cmd = config.effective_pi_command()
    assert "--append-system-prompt" in cmd
    assert "Vibes" in cmd
    assert "--model" not in cmd
    assert "--thinking" not in cmd


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


def test_config_prompt_from_settings(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(json.dumps({
        "prompt": "Always respond in Portuguese",
    }))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIBES_PROMPT", raising=False)
    config = Config()
    assert config.prompt == "Always respond in Portuguese"


def test_config_prompt_default_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIBES_PROMPT", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
    config = Config()
    assert config.prompt == ""


def test_config_prompt_env_overrides_file(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(json.dumps({
        "prompt": "from file",
    }))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VIBES_PROMPT", "from env")
    config = Config()
    assert config.prompt == "from env"


def test_effective_pi_command_with_prompt():
    config = Config()
    config.pi_model = None
    config.pi_thinking = None
    config.prompt = "Be terse"
    cmd = config.effective_pi_command()
    assert "--append-system-prompt" in cmd
    assert "Be terse" in cmd
    assert "Vibes" in cmd  # base prompt still included


def test_effective_pi_command_no_prompt():
    config = Config()
    config.pi_model = None
    config.pi_thinking = None
    config.prompt = ""
    cmd = config.effective_pi_command()
    assert "Vibes" in cmd
    assert "Be terse" not in cmd


def test_settings_file_cwd_over_xdg(tmp_path, monkeypatch):
    """CWD .vibes/ takes priority over XDG."""
    local_dir = tmp_path / ".vibes"
    local_dir.mkdir()
    (local_dir / "settings.json").write_text('{"port": 1111}')
    xdg_dir = tmp_path / "xdg" / "vibes"
    xdg_dir.mkdir(parents=True)
    (xdg_dir / "settings.json").write_text('{"port": 2222}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    result = _find_settings_file()
    assert ".vibes" in str(result)


def test_load_settings_file_malformed(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text("not json {{{")
    monkeypatch.chdir(tmp_path)
    assert _load_settings_file() == {}


def test_load_settings_file_non_object(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text('"just a string"')
    monkeypatch.chdir(tmp_path)
    assert _load_settings_file() == {}


def test_resolve_str_from_file():
    assert _resolve({"agent_name": "mybox"}, "agent_name", "VIBES_AGENT_NAME", "default", "str") == "mybox"


def test_resolve_int_invalid_in_file():
    assert _resolve({"port": "abc"}, "port", "VIBES_PORT", 8080, "int") == 8080


def test_resolve_bool_non_string_non_bool():
    assert _resolve({"debug": 42}, "debug", "VIBES_DEBUG", False, "bool") is False


def test_resolve_none_str_returns_default():
    assert _resolve({"pi_model": None}, "pi_model", "VIBES_PI_MODEL", None, "str") is None


def test_settings_file_diagnostics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
    config = Config()
    assert config.settings_file is None


# --- save_setting tests ---

def test_save_setting_creates_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "nonexistent"))
    save_setting("pi_model", "openai/gpt-4")
    data = json.loads((tmp_path / ".vibes" / "settings.json").read_text())
    assert data["pi_model"] == "openai/gpt-4"


def test_save_setting_preserves_existing(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(json.dumps({"port": 3000}))
    monkeypatch.chdir(tmp_path)
    save_setting("pi_model", "test/model")
    data = json.loads((settings_dir / "settings.json").read_text())
    assert data["port"] == 3000
    assert data["pi_model"] == "test/model"


def test_save_setting_removes_on_none(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(json.dumps({"pi_model": "old", "port": 3000}))
    monkeypatch.chdir(tmp_path)
    save_setting("pi_model", None)
    data = json.loads((settings_dir / "settings.json").read_text())
    assert "pi_model" not in data
    assert data["port"] == 3000


def test_save_setting_removes_on_empty_string(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(json.dumps({"prompt": "hello"}))
    monkeypatch.chdir(tmp_path)
    save_setting("prompt", "")
    data = json.loads((settings_dir / "settings.json").read_text())
    assert "prompt" not in data


def test_save_setting_updates_existing_key(tmp_path, monkeypatch):
    settings_dir = tmp_path / ".vibes"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(json.dumps({"pi_model": "old"}))
    monkeypatch.chdir(tmp_path)
    save_setting("pi_model", "new/model")
    data = json.loads((settings_dir / "settings.json").read_text())
    assert data["pi_model"] == "new/model"


def test_save_setting_writes_to_existing_file_location(tmp_path, monkeypatch):
    """save_setting writes to an existing XDG file rather than creating .vibes/ in cwd."""
    xdg_dir = tmp_path / "xdg" / "vibes"
    xdg_dir.mkdir(parents=True)
    (xdg_dir / "settings.json").write_text(json.dumps({"port": 5000}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    save_setting("pi_thinking", "high")
    data = json.loads((xdg_dir / "settings.json").read_text())
    assert data["pi_thinking"] == "high"
    assert data["port"] == 5000
    assert not (tmp_path / ".vibes").exists()
