"""Opt-in real FFI + loopback fake inference. Never calls an external model.

Requires an explicit provisioned COPILOT_CLI_PATH. Uses a fresh profile and
synthetic content only; inspects actual persistence through public SDK APIs.
"""

import asyncio
import json
import os
from pathlib import Path
import tempfile
import sys
import time
import uuid

runtime = os.environ.get("COPILOT_CLI_PATH")
if not runtime:
    raise SystemExit("Provisioned COPILOT_CLI_PATH required")
root = Path(tempfile.mkdtemp(prefix="vibes-persistence-"))
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
    COPILOT_HOME=str(root / "state"),
    COPILOT_CLI_PATH=runtime,
    COPILOT_SKIP_CLI_DOWNLOAD="1",
    COPILOT_DISABLE_KEYTAR="1",
)
os.chdir(root)
from aiohttp import web  # noqa: E402
from copilot import CopilotClient, RuntimeConnection, RemoteSessionMode  # noqa: E402
from copilot.generated.rpc import SessionsSaveRequest, PermissionDecisionReject  # noqa: E402


async def main():
    calls = []
    slow_entered, slow_release = asyncio.Event(), asyncio.Event()
    scenario = {"stage": None, "tools": [], "tool_results": []}

    async def model(request):
        body = await request.json()
        request_text = json.dumps(body.get("messages", []))
        (root/'last-request.json').write_text(json.dumps(body,indent=2),encoding='utf8')
        scenario["image_seen"] = (
            scenario.get("image_seen", False)
            or "data:image/png;base64," in request_text
        )
        scenario["document_seen"] = (
            scenario.get("document_seen", False)
            or "document-input-marker" in request_text
        )
        calls.append(
            {
                "path": request.path,
                "model": body.get("model"),
                "stream": body.get("stream"),
            }
        )
        print("FAKE", json.dumps(calls[-1]), flush=True)
        if scenario.get('slow_turn'):
            slow_entered.set()
            await slow_release.wait()
            return web.json_response({'error':'synthetic aborted request'},status=503)
        msg = {
            "role": "assistant",
            "content": "Synthetic reply: persistence marker blue-47.",
        }
        tool_call = None
        if scenario["stage"] is not None:
            tools = {
                t["function"]["name"]: t["function"] for t in body.get("tools", [])
            }
            scenario["tools"] = sorted(tools)
            scenario["tool_results"] = [
                m.get("content")
                for m in body.get("messages", [])
                if m.get("role") == "tool"
            ]
            stages = [
                (
                    "ask_user",
                    {
                        "question": "Synthetic choice?",
                        "choices": ["One", "Two"],
                        "allow_freeform": True,
                    },
                ),
                ("plan", {"action": "read"}),
                ("vibes_attach_file", {"path": "synthetic-output.txt"}),
                ("fixture-echo", {"text": "mcp-marker"}),
            ]
            if scenario.get("deny_turn"):
                stages = [
                    ("view", {"path": str(root.parent / "outside-synthetic.txt")})
                ]
            if scenario["stage"] < len(stages):
                name, args = stages[scenario["stage"]]
                if name not in tools:
                    raise RuntimeError(
                        f"Missing fixture tool {name}; available: {sorted(tools)}"
                    )
                print("TOOL_SCHEMA", name, json.dumps(tools[name]), flush=True)
                tool_call = {
                    "index": 0,
                    "id": f"fixture-{scenario['stage']}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
                scenario["stage"] += 1
        if not body.get("stream"):
            return web.json_response(
                {
                    "id": "fixture",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": "gpt-4.1",
                    "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 8,
                        "total_tokens": 18,
                    },
                }
            )
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        chunks = (
            [
                ({"role": "assistant"}, None),
                ({"tool_calls": [tool_call]}, None),
                ({}, "tool_calls"),
            ]
            if tool_call
            else [
                ({"role": "assistant"}, None),
                ({"content": msg["content"]}, None),
                ({}, "stop"),
            ]
        )
        for delta, reason in chunks:
            data = {
                "id": "fixture",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "gpt-4.1",
                "choices": [{"index": 0, "delta": delta, "finish_reason": reason}],
            }
            await response.write(("data: " + json.dumps(data) + "\n\n").encode())
        await response.write(b"data: [DONE]\n\n")
        return response

    app = web.Application()
    app.router.add_post("/v1/chat/completions", model)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    opts = dict(
        on_permission_request=lambda *_: PermissionDecisionReject(),
        model="gpt-4.1",
        available_tools=[],
        streaming=True,
        remote_session=RemoteSessionMode.OFF,
        provider={
            "type": "openai",
            "wire_api": "completions",
            "base_url": f"http://127.0.0.1:{port}/v1",
            "api_key": "synthetic-not-a-secret",
        },
        working_directory=str(root),
    )
    result = {
        "fixture": str(root),
        "externalModelCalls": 0,
        "transport": "ffi",
        "events": [],
    }
    client = CopilotClient(
        connection=RuntimeConnection.for_inprocess(),
        base_directory=str(root / "state"),
        use_logged_in_user=False,
        mode="empty",
        log_level="error",
    )
    try:
        await asyncio.wait_for(client.start(), 20)
        session = await client.create_session(session_id=str(uuid.uuid4()), **opts)
        session.on(
            lambda e: result["events"].append(str(getattr(e.type, "value", e.type)))
        )
        sid = session.session_id
        await asyncio.wait_for(
            session.send_and_wait("Reply with the synthetic marker.", timeout=20), 25
        )
        await client.rpc.sessions.save(SessionsSaveRequest(session_id=sid))
        result["filesBeforeStop"] = [
            str(p.relative_to(root)) for p in root.rglob("events.jsonl")
        ]
        await client.stop()
        client = CopilotClient(
            connection=RuntimeConnection.for_inprocess(),
            base_directory=str(root / "state"),
            use_logged_in_user=False,
            mode="empty",
            log_level="error",
        )
        await client.start()
        resumed = await client.resume_session(sid, continue_pending_work=False, **opts)
        history = await resumed.get_events()
        result["resumed"] = resumed.session_id == sid
        result["historyEvents"] = len(history)
        result["markerPresent"] = any(
            "blue-47"
            in json.dumps(
                e.to_dict() if hasattr(e, "to_dict") else vars(e), default=str
            )
            for e in history
        )
        result["passed"] = result["resumed"] and result["markerPresent"]
        if "--vibes" in sys.argv:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
            from vibes.copilot_client import CopilotBackend
            from vibes.config import get_config
            from vibes.db import init_db, close_db, get_db
            from vibes.sessions import SessionStore
            from vibes import agent_attachments

            config = get_config()
            config.copilot_state_dir = str(root / "vibes-native")
            config.copilot_model = "gpt-4.1"
            mcp_script = root / "fixture-mcp.py"
            mcp_script.write_text(
                """import json, sys
for line in sys.stdin:
 r=json.loads(line); method=r.get('method')
 if 'id' not in r: continue
 if method=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}}
 elif method=='tools/list': result={'tools':[{'name':'echo','description':'Synthetic echo','inputSchema':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}}]}
 elif method=='tools/call': result={'content':[{'type':'text','text':r['params']['arguments']['text']}]}
 else: result={}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
""",
                encoding="utf8",
            )
            config.copilot_mcp_servers = {
                "fixture": {
                    "type": "local",
                    "command": sys.executable,
                    "args": [str(mcp_script)],
                    "tools": ["echo"],
                }
            }
            config.copilot_available_tools = [
                "builtin:ask_user",
                "builtin:view",
                "mcp:fixture-echo",
            ]
            skill_dir = root / "skills" / "synthetic"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: synthetic\ndescription: Synthetic fixture skill\n---\nReturn blue-47 when requested.\n",
                encoding="utf8",
            )
            config.copilot_skill_directories = [str(root / "skills")]
            (root / "synthetic-output.txt").write_text(
                "synthetic delivery", encoding="utf8"
            )
            backend = CopilotBackend()
            decisions = []

            async def decide(payload):
                decisions.append(payload)
                if payload["allow_freeform"]:
                    assert backend.respond(
                        payload["request_id"], "freeform", "Synthetic freeform"
                    )
                else:
                    outcome = (
                        "deny"
                        if payload["tool_call"]["rawInput"].get("kind") == "read"
                        else "allow"
                    )
                    assert backend.respond(payload["request_id"], outcome)

            backend.request_callback = decide
            await init_db(str(root / "vibes.db"))
            await backend.start()

            async def fixture_client(real):
                # Test-only provider injection. Never available through browser config.
                async def create(**kw):
                    return await real.create_session(provider=opts["provider"], **kw)

                async def resume(sid, **kw):
                    return await real.resume_session(
                        sid, provider=opts["provider"], **kw
                    )

                from types import SimpleNamespace

                return SimpleNamespace(
                    create_session=create,
                    resume_session=resume,
                    rpc=real.rpc,
                    stop=real.stop,
                )

            backend.client = await fixture_client(backend.client)
            store = SessionStore(await get_db())
            context = {
                "mode": "copilot-ffi",
                "session_id": "default",
                "thread_id": 1,
                "turn_id": "test",
                "receipts": {},
                "agent_id": "default",
            }
            agent_attachments.active = context
            try:
                statuses = []

                async def callback(data):
                    statuses.append(data)

                import io
                from PIL import Image

                image = io.BytesIO()
                Image.new("RGB", (2, 2), color="blue").save(image, format="PNG")
                database = await get_db()
                metadata = {"source": "composer-upload", "session_id": "default"}
                image_id = await database.create_media(
                    "synthetic.png", "image/png", image.getvalue(), metadata=metadata
                )
                doc_id = await database.create_media(
                    "synthetic.txt",
                    "text/plain",
                    b"document-input-marker",
                    metadata=metadata,
                )
                scenario["stage"] = 0
                answer = await asyncio.wait_for(
                    backend.send(
                        "Synthetic adapter test.",
                        1,
                        callback,
                        chat_id="default",
                        store=store,
                        media_ids=[image_id, doc_id],
                    ),
                    60,
                )
                result["adapterDiagnostic"] = {
                    "answer": answer,
                    "statuses": statuses,
                    "decisions": decisions,
                    "scenario": scenario,
                }
                assert "blue-47" in answer["text"]
                skills = await backend.sessions["default"].rpc.skills.list(timeout=5)
                result["skills"] = skills.to_dict()
                assert "synthetic" in json.dumps(result["skills"])
                assert scenario["image_seen"] and scenario["document_seen"]
                binding = await store.backend_binding("default", "copilot-ffi")
                await backend.stop()
                await backend.start()
                backend.client = await fixture_client(backend.client)
                resumed = await backend._session("default", store)
                assert resumed.session_id == binding["conversation_id"]
                assert any(
                    "blue-47" in json.dumps(e.to_dict(), default=str)
                    for e in await resumed.get_events()
                )
                result["vibesAdapter"] = {
                    "streamedChunks": len(statuses),
                    "replyVerified": True,
                    "coldResumeVerified": True,
                    "decisions": len(decisions),
                    "scenario": dict(scenario),
                }
                assert len(decisions) >= 2
                results = json.dumps(scenario["tool_results"])
                assert "Synthetic freeform" in results and "mcp-marker" in results
                assert "synthetic-output.txt" in results
                scenario.update(stage=0, deny_turn=True)
                agent_attachments.active = {**context, "turn_id": "deny-test"}
                denied = await asyncio.wait_for(
                    backend.send(
                        "Synthetic denial test.",
                        1,
                        callback,
                        chat_id="default",
                        store=store,
                    ),
                    30,
                )
                assert (
                    'without a text response' in denied["text"] and not backend.pending and not backend.poisoned
                )
                assert decisions[-1]["tool_call"]["rawInput"]["kind"] == "read"
                result["deniedReadVerified"] = True
                state=await backend.model('default',store)
                assert state['model']['id']=='gpt-4.1'
                result['nativeModelStateVerified']=True
                scenario.update(stage=None,slow_turn=True)
                agent_attachments.active={**context,'turn_id':'abort-test'}
                cancelling=asyncio.create_task(backend.send('Synthetic slow request.',1,callback,chat_id='default',store=store))
                await asyncio.wait_for(slow_entered.wait(),15)
                assert await backend.abort('default',backend.active)
                cancelled=await asyncio.wait_for(cancelling,15)
                assert cancelled['cancelled'] and not backend.poisoned
                slow_release.set()
                result['nativeCancellationVerified']=True
                await backend.stop()
                child=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name('ffi_resume_child.py')),
                    stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                try:
                    stdout,stderr=await asyncio.wait_for(child.communicate(json.dumps({'root':str(root),
                        'state':str(root/'vibes-native'),'session':binding['conversation_id'],'provider':opts['provider']}).encode()),30)
                    assert child.returncode == 0, stderr.decode(errors='replace')
                    result['freshProcessResume']=json.loads(stdout)
                    assert result['freshProcessResume']['pid'] != os.getpid()
                finally:
                    if child.returncode is None:
                        child.kill()
                        await child.wait()
            finally:
                agent_attachments.active = None
                await backend.stop()
                await close_db()
    except Exception as e:
        import traceback

        result.update(passed=False, error=repr(e), traceback=traceback.format_exc())
    finally:
        slow_release.set()
        await client.stop()
        await runner.cleanup()
    result["fakeRequests"] = calls
    (root / "result.json").write_text(json.dumps(result, indent=2), encoding="utf8")
    print(json.dumps(result, indent=2))
    if not result.get("passed"):
        raise SystemExit(1)


asyncio.run(main())
