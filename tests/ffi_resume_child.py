"""Child of ffi_persistence_smoke.py: prove journal resume in a fresh OS process.

Accepts synthetic fixture metadata on stdin; refuses non-loopback providers.
Never signs in or sends a model prompt. Not collected by pytest.
"""

import asyncio
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit


async def main():
    payload = json.loads(sys.stdin.readline())
    runtime = os.environ.get("COPILOT_CLI_PATH")
    if not runtime or urlsplit(payload["provider"]["base_url"]).hostname != "127.0.0.1":
        raise RuntimeError("Explicit runtime and loopback synthetic provider required")
    root = Path(payload["root"])
    keep = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}
    }
    os.environ.clear()
    os.environ.update(keep)
    os.environ.update(
        HOME=str(root),
        USERPROFILE=str(root),
        LOCALAPPDATA=str(root / "local"),
        APPDATA=str(root / "roaming"),
        TEMP=str(root),
        TMP=str(root),
        COPILOT_CLI_PATH=runtime,
        COPILOT_SKIP_CLI_DOWNLOAD="1",
        COPILOT_DISABLE_KEYTAR="1",
    )
    os.chdir(root)
    from copilot import CopilotClient, RuntimeConnection, RemoteSessionMode
    from copilot.generated.rpc import PermissionDecisionReject

    client = CopilotClient(
        connection=RuntimeConnection.for_inprocess(),
        base_directory=payload["state"],
        use_logged_in_user=False,
        mode="empty",
        log_level="error",
    )
    try:
        await client.start()
        session = await client.resume_session(
            payload["session"],
            continue_pending_work=False,
            on_permission_request=lambda *_: PermissionDecisionReject(),
            available_tools=[],
            remote_session=RemoteSessionMode.OFF,
            provider=payload["provider"],
            working_directory=str(root),
        )
        events = await session.get_events()
        marker = any("blue-47" in json.dumps(e.to_dict(), default=str) for e in events)
        assert marker and session.session_id == payload["session"]
        print(
            json.dumps(
                {
                    "freshProcess": True,
                    "pid": os.getpid(),
                    "historyEvents": len(events),
                    "markerPresent": marker,
                }
            ),
            flush=True,
        )
    finally:
        await client.stop()


asyncio.run(main())
