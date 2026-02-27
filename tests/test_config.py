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

_default_pi_agent_command = importlib.import_module("vibes.config")._default_pi_agent_command
PI_PROMPT_PREFIX = importlib.import_module("vibes.pi_prompt").PI_PROMPT_PREFIX
Config = importlib.import_module("vibes.config").Config


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
