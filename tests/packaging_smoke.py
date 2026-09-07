"""Run with the installed Python, outside an editable/source-tree import path."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

import vibes


def main():
    package = Path(vibes.__file__).parent
    for relative in (
        "static/dist/app.js", "static/dist/app.css",
        "extensions/pi-vibes-tools.ts",
    ):
        assert (package / relative).is_file(), relative
    subprocess.run([sys.executable, "-I", "-m", "vibes.messages_mcp", "--help"],
                   check=True, stdout=subprocess.PIPE)
    with tempfile.TemporaryDirectory(prefix="vibes-installed-") as directory:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {key: value for key, value in os.environ.items() if not key.startswith("VIBES_")}
        env.update(VIBES_HOST="127.0.0.1", VIBES_PORT=str(port),
                   VIBES_ACP_AGENT="/nonexistent-packaging-smoke-agent",
                   VIBES_PI_ENABLED="false", XDG_CONFIG_HOME=directory)
        with open(Path(directory) / "server.log", "w+") as log:
            process = subprocess.Popen([sys.executable, "-I", "-m", "vibes.app"],
                                       cwd=directory, env=env, stdout=log, stderr=log)
            try:
                root = f"http://127.0.0.1:{port}"
                for _ in range(100):
                    try:
                        with urlopen(root + "/health", timeout=1) as response:
                            assert response.status == 200
                        break
                    except (URLError, TimeoutError):
                        if process.poll() is not None:
                            raise RuntimeError("Installed server exited during startup")
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Installed server did not become healthy")
                for path in ("/", "/static/dist/app.js", "/static/dist/app.css"):
                    with urlopen(root + path, timeout=5) as response:
                        assert response.status == 200, path
                        assert response.read(100), path
                print("Installed package: health, page, JS/CSS and extension checks passed")
            except Exception:
                log.seek(0)
                print(log.read(), file=sys.stderr)
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
