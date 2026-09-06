"""Opt-in local terminal transport. Cookie ownership is independent of frame data."""
import asyncio
import codecs
import json
import os
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from aiohttp import web
from vibes.terminal import TerminalService

COOKIE = "vibes_terminal_owner"
KEY = web.AppKey("terminal_adapter", object)


class TerminalAdapter:
    def __init__(self, cwd, enabled=False, grace=15, handoff_ttl=30):
        self.enabled = enabled
        self.service = TerminalService(cwd)
        self.owners = set()
        self.sockets = {}
        self.timers = {}
        self.handoffs = {}
        self.grace = grace
        self.handoff_ttl = handoff_ttl

    def owner(self, request):
        if not self.enabled:
            raise web.HTTPNotFound()
        origin = request.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != request.scheme or parsed.netloc != request.host:
                raise web.HTTPForbidden()
        elif request.path.endswith("/ws") or request.method != "GET":
            raise web.HTTPForbidden(reason="Origin required")
        owner = request.cookies.get(COOKIE)
        if owner not in self.owners:
            raise web.HTTPUnauthorized()
        return owner

    async def info(self, request):
        if not self.enabled:
            return web.json_response({"enabled": False})
        origin = request.headers.get("Origin")
        if origin and origin != f"{request.scheme}://{request.host}":
            raise web.HTTPForbidden()
        owner = request.cookies.get(COOKIE)
        if owner not in self.owners:
            if len(self.owners) >= 128:
                raise web.HTTPServiceUnavailable(reason="Terminal owner limit")
            owner = secrets.token_urlsafe(32)
            self.owners.add(owner)
        response = web.json_response({"enabled": True, "ws_path": "/terminal/ws",
            "cwd": str(self.service.cwd), "shell": self.service.shell,
            "active": owner in self.service.sessions,
            "connected_clients": int(owner in self.sockets)})
        response.set_cookie(COOKIE, owner, httponly=True, samesite="Strict", secure=request.secure)
        response.headers["Cache-Control"] = "no-store"
        return response

    async def handoff(self, request):
        owner = self.owner(request)
        if owner not in self.sockets:
            raise web.HTTPConflict(reason="No connected terminal")
        self.handoffs = {k: v for k, v in self.handoffs.items() if v[1] > time.monotonic() and v[0] != owner}
        token = secrets.token_urlsafe(32)
        self.handoffs[token] = (owner, time.monotonic() + self.handoff_ttl)
        return web.json_response({"handoff": {"token": token, "expires_at": datetime.fromtimestamp(time.time() + self.handoff_ttl, timezone.utc).isoformat()}}, headers={"Cache-Control": "no-store"})

    async def expire(self, owner):
        try:
            await asyncio.sleep(self.grace)
            session = self.service.sessions.get(owner)
            if owner not in self.sockets and session:
                await self.service.close(session)
        finally:
            self.timers.pop(owner, None)

    async def websocket(self, request):
        owner = self.owner(request)
        token = request.query.get("handoff")
        old = self.sockets.get(owner)
        if token:
            record = self.handoffs.get(token)
            if not record or record[0] != owner or record[1] <= time.monotonic():
                raise web.HTTPForbidden(reason="Invalid handoff")
            del self.handoffs[token]
        elif old:
            raise web.HTTPConflict(reason="Terminal already attached; handoff required")
        # Reserve ownership before awaiting so concurrent upgrades cannot both attach.
        socket = web.WebSocketResponse(max_msg_size=70000, heartbeat=20)
        self.sockets[owner] = socket
        timer = self.timers.pop(owner, None)
        if timer:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)
        session = None
        sender = None
        queue = asyncio.Queue(maxsize=64)
        try:
            await socket.prepare(request)
            if old:
                await old.close(code=1000, message=b"terminal handoff")
            session = await self.service.open(owner)
            session.clients.add(queue)
            await socket.send_json({"type": "session", "cwd": str(self.service.cwd), "shell": self.service.shell,
                "session_id": session.session_id, "created_at": session.created_at,
                "process_pid": session.process.pid})
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            if session.history:
                await socket.send_json({"type": "output", "data": decoder.decode(bytes(session.history))})

            async def send_output():
                while not socket.closed:
                    try:
                        data = await asyncio.wait_for(queue.get(), 0.2)
                        await socket.send_json({"type": "output", "data": decoder.decode(data)})
                    except asyncio.TimeoutError:
                        if session.process.returncode is not None:
                            await socket.send_json({"type": "exit", "exit_code": session.process.returncode})
                            await socket.close()
                            return
                        if queue not in session.clients:
                            await socket.close(code=1013, message=b"Terminal output consumer too slow")
                            return

            sender = asyncio.create_task(send_output())
            async for message in socket:
                if message.type != web.WSMsgType.TEXT:
                    continue
                try:
                    frame = json.loads(message.data)
                    if frame.get("type") == "input" and isinstance(frame.get("data"), str):
                        await self.service.write(session, frame["data"].encode())
                    elif frame.get("type") == "ping":
                        await socket.send_json({"type": "pong", "ts": frame.get("ts")})
                    elif frame.get("type") == "resize":
                        self.service.resize(session, frame["cols"], frame["rows"])
                    else:
                        raise ValueError("Unknown terminal frame")
                except (ValueError, TypeError, KeyError, AttributeError, OSError):
                    await socket.close(code=1008, message=b"Invalid terminal frame")
        finally:
            if session:
                session.clients.discard(queue)
            if self.sockets.get(owner) is socket:
                del self.sockets[owner]
                self.timers[owner] = asyncio.create_task(self.expire(owner))
            if sender:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
        return socket

    async def cleanup(self, app):
        for timer in self.timers.values():
            timer.cancel()
        await asyncio.gather(*list(self.timers.values()), return_exceptions=True)
        for socket in list(self.sockets.values()):
            await socket.close(code=1001)
        for timer in list(self.timers.values()):
            timer.cancel()
        await asyncio.gather(*list(self.timers.values()), return_exceptions=True)
        await self.service.shutdown()


def setup_routes(app):
    adapter = TerminalAdapter(os.getcwd(), os.environ.get("VIBES_ENABLE_TERMINAL", "").lower() in {"1", "true"})
    app[KEY] = adapter
    app.router.add_get("/terminal/session", adapter.info)
    app.router.add_post("/terminal/handoff", adapter.handoff)
    app.router.add_get("/terminal/ws", adapter.websocket)
    app.on_shutdown.append(adapter.cleanup)
