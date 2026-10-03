"""Six real FFI sessions via HTTP; fake loopback inference, isolated profile only."""

import asyncio
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from types import SimpleNamespace

root = Path(tempfile.mkdtemp(prefix="vibes-concurrency-"))
runtime = os.environ.get("COPILOT_CLI_PATH")
if not runtime:
    raise SystemExit("Explicit provisioned native runtime required")
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
    APPDATA=str(root / "roaming"),
    LOCALAPPDATA=str(root / "local"),
    TEMP=str(root),
    TMP=str(root),
    COPILOT_CLI_PATH=runtime,
    COPILOT_SKIP_CLI_DOWNLOAD="1",
    COPILOT_DISABLE_KEYTAR="1",
    VIBES_DEFAULT_AGENT="copilot-ffi",
    VIBES_COPILOT_MODEL="gpt-4.1",
    VIBES_COPILOT_USE_LOGGED_IN_USER="false",
    VIBES_COPILOT_STATE_DIR=str(root / "native"),
    VIBES_DB_PATH=str(root / "vibes.db"),
    XDG_CONFIG_HOME=str(root / "config"),
)
os.chdir(root)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aiohttp import web, ClientSession, ClientTimeout  # noqa: E402
from vibes.app import create_app  # noqa: E402
from vibes.copilot_host import backend  # noqa: E402
from vibes.config import get_config  # noqa: E402
from vibes.db import get_db  # noqa: E402
from vibes.sessions import SessionStore  # noqa: E402


async def main():
    calls, entered = {}, set()
    concurrent = asyncio.Event()
    result = {
        "transport": "ffi",
        "fixture": str(root),
        "externalModelCalls": 0,
        "passed": False,
    }

    async def model(request):
        body = await request.json()
        raw = json.dumps(body.get("messages", []))
        match = re.search(r"fixture-lane-[0-5]", raw)
        if not match:
            raise ValueError("No synthetic chat marker")
        label = match[0]
        stage = calls.get(label, 0)
        calls[label] = stage + 1
        entered.add(label)
        if len(entered) == 6:
            concurrent.set()
        await asyncio.wait_for(concurrent.wait(), 20)
        tools = [
            ("ask_user", {"question": "Question for " + label, "allow_freeform": True}),
            ("plan", {"action": "read"}),
            ("vibes_attach_file", {"path": label + ".txt"}),
        ]
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        if stage < len(tools):
            name, args = tools[stage]
            call = {
                "index": 0,
                "id": label + "-" + str(stage),
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
            chunks = [
                ({"role": "assistant"}, None),
                ({"tool_calls": [call]}, None),
                ({}, "tool_calls"),
            ]
        else:
            chunks = [
                ({"role": "assistant"}, None),
                ({"content": "Completed " + label}, None),
                ({}, "stop"),
            ]
        for delta, finish in chunks:
            packet = {
                "id": label,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "gpt-4.1",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            await response.write(("data: " + json.dumps(packet) + "\n\n").encode())
        await response.write(b"data: [DONE]\n\n")
        return response

    inference = web.Application()
    inference.router.add_post("/v1/chat/completions", model)
    ir = web.AppRunner(inference)
    await ir.setup()
    site = web.TCPSite(ir, "127.0.0.1", 0)
    await site.start()
    provider = {
        "type": "openai",
        "wire_api": "completions",
        "base_url": f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/v1",
        "api_key": "synthetic",
    }
    config = get_config()
    config.copilot_available_tools = ["builtin:ask_user"]
    config.permission_timeout = 10
    runner = web.AppRunner(create_app())
    await runner.setup()
    real = backend.client

    async def create(**kwargs):
        return await real.create_session(provider=provider, **kwargs)

    async def resume(sid, **kwargs):
        return await real.resume_session(sid, provider=provider, **kwargs)

    backend.client = SimpleNamespace(
        create_session=create, resume_session=resume, rpc=real.rpc, stop=real.stop
    )
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"
    try:
        database = await get_db()
        store = SessionStore(database)
        ids = ["default"] + [
            (await store.create("Synthetic " + str(i)))["id"] for i in range(1, 6)
        ]
        for i in range(6):
            (root / f"fixture-lane-{i}.txt").write_text(
                "output-" + str(i), encoding="utf8"
            )
        async with ClientSession(timeout=ClientTimeout(total=30)) as http:

            async def status(chat):
                async with http.get(
                    url + "/agents/status", params={"session_id": chat}
                ) as response:
                    return await response.json()

            async def post(path, data):
                async with http.post(url + path, json=data) as response:
                    body = await response.json()
                    assert response.status < 300, (response.status, body)
                    return body

            await asyncio.gather(
                *(
                    post(
                        "/agent/default/message",
                        {"session_id": chat, "content": f"fixture-lane-{i}"},
                    )
                    for i, chat in enumerate(ids)
                )
            )
            async with asyncio.timeout(25):
                while True:
                    statuses = await asyncio.gather(*(status(chat) for chat in ids))
                    if all(s["pending_requests"] for s in statuses):
                        break
                    await asyncio.sleep(0.03)
            assert len(entered) == 6
            assert backend.status()["active_chats"] == 6
            result["simultaneousNativeTurns"] = 6
            first_pending = [s["pending_requests"][0]["request_id"] for s in statuses]
            await post(
                "/agent/default/abort",
                {
                    "session_id": ids[0],
                    "turn_id": statuses[0]["active_turns"][0]["turn_id"],
                },
            )
            # Leave lane 1 unanswered so its permission deadline expires while
            # the other lanes finish independently.
            for i in range(2, 6):
                await post(
                    "/agent/respond",
                    {
                        "request_id": first_pending[i],
                        "outcome": "freeform",
                        "answer": f"answer-{i}",
                    },
                )
            answered = set(first_pending)
            async with asyncio.timeout(40):
                while True:
                    statuses = await asyncio.gather(*(status(chat) for chat in ids))
                    for i in range(2, 6):
                        for request in statuses[i]["pending_requests"]:
                            assert request["session_id"] == ids[i]
                            if request["request_id"] not in answered:
                                answered.add(request["request_id"])
                                await post(
                                    "/agent/respond",
                                    {
                                        "request_id": request["request_id"],
                                        "outcome": "allow",
                                    },
                                )
                    if not any(s["busy"] for s in statuses):
                        break
                    await asyncio.sleep(0.03)
            outputs = []
            for i, chat in enumerate(ids):
                timeline = await store.timeline(chat)
                texts = " ".join(
                    p["data"].get("content", "") for p in timeline["posts"]
                )
                if i >= 2:
                    assert "Completed fixture-lane-" + str(i) in texts, texts
                    attachment = [
                        p for p in timeline["posts"] if p["data"].get("media_ids")
                    ]
                    assert len(attachment) == 1
                    media = await database.get_media_data(
                        attachment[0]["data"]["media_ids"][0]
                    )
                    assert media[1] == ("output-" + str(i)).encode()
                    outputs.append({"lane": i, "mediaScoped": True})
                for other in range(6):
                    if other != i:
                        assert "Completed fixture-lane-" + str(other) not in texts
            async with http.post(
                url + "/agent/respond",
                json={"request_id": first_pending[0], "outcome": "allow"},
            ) as replay:
                assert replay.status == 409
            async with http.post(
                url + "/agent/respond",
                json={
                    "request_id": first_pending[1],
                    "outcome": "freeform",
                    "answer": "too late",
                },
            ) as timeout_replay:
                assert timeout_replay.status == 409
            result.update(
                passed=True,
                cancelScoped=True,
                permissionTimeoutScoped=True,
                staleApprovalRejected=True,
                outputs=outputs,
                remainingActiveTurns=len(await database.get_active_turns()),
                calls=calls,
            )
    except Exception as exc:
        import traceback

        result.update(error=repr(exc), traceback=traceback.format_exc())
    finally:
        await runner.cleanup()
        await ir.cleanup()
        (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


asyncio.run(main())
