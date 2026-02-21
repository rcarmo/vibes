import shlex
import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) in sys.path:
    sys.path.remove(str(SRC_PATH))
sys.path.insert(0, str(SRC_PATH))

for module_name in list(sys.modules.keys()):
    if module_name == "vibes" or module_name.startswith("vibes."):
        sys.modules.pop(module_name, None)

from vibes.config import _default_pi_agent_command
from vibes.pi_prompt import PI_PROMPT_PREFIX


def test_default_pi_agent_command_includes_prompt_and_extension():
    cmd = _default_pi_agent_command()
    assert "--append-system-prompt" in cmd
    assert "pi-vibes-tools.ts" in cmd
    assert shlex.quote(PI_PROMPT_PREFIX) in cmd
    ext_path = Path(__file__).resolve().parents[1] / "src" / "vibes" / "extensions" / "pi-vibes-tools.ts"
    assert str(ext_path) in cmd
