"""Opt-in, loopback-only VNC-over-WebSocket transport.

This is deliberately an opaque byte relay.  VNC/RFB authentication and protocol
negotiation remain between the browser VNC client and the local VNC server.
"""
import asyncio
import ipaddress
import os
import secrets
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from aiohttp import web

COOKIE = "vibes_vnc_owner"
KEY = web.AppKey("vnc_adapter", object)

MAX_FRAME = 64 * 1024
OWNER_LIMIT = 128
HANDOFF_TTL = 30
GRACE_SECONDS = 15
CONNECT_TIMEOUT = 5
WRITE_TIMEOUT = 15


class _Tunnel:
    def __init__(self, owner, reader, writer):
        self.owner = owner
        self.reader = reader
        self.writer = writer
        self.socket = None
        self.attached = asyncio.Event()
        self.lock = asyncio.Lock()
        self.closed = False
        self.forwarder = None


class VNCAdapter:
    """Owns bounded, per-browser TCP relays to one configured loopback target."""

    def __init__(
        self,
        enabled=False,
        host="127.0.0.1",
        port=5901,
        grace=GRACE_SECONDS,
        handoff_ttl=HANDOFF_TTL,
    ):
        self.requested = enabled
        self.host, self.port = self._target(host, port)
        self.configured = self.host is not None
        self.enabled = bool(enabled and self.configured)
        self.target = self._format_target(self.host, self.port) if self.configured else None
        self.grace = grace
        self.handoff_ttl = handoff_ttl
        self.owners = set()
        self.tunnels = {}
        self.opening = set()
        self.timers = {}
        self.handoffs = {}

    @staticmethod
    def _target(host, port):
        if not isinstance(host, str):
            return None, None
        host = host.strip()
        # This compatibility spelling is normalized before any connection call;
        # it is never passed to a resolver.
        if host.lower() == "localhost":
            host = "127.0.0.1"
        try:
            address = ipaddress.ip_address(host)
            port = int(port)
        except (ValueError, TypeError):
            return None, None
        if not address.is_loopback or not 1 <= port <= 65535:
            return None, None
        return str(address), port

    @staticmethod
    def _format_target(host, port):
        return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"

    @staticmethod
    def _same_origin(request):
        origin = request.headers.get("Origin")
        if not origin:
            return False
        parsed = urlsplit(origin)
        return (
            parsed.scheme == request.scheme
            and parsed.netloc == request.host
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
        )

    def _require_target_query(self, request, *, handoff=False):
        allowed = {"target"}
        if handoff:
            allowed.add("handoff")
        for name in request.query:
            if name not in allowed:
                raise web.HTTPBadRequest(reason="Unsupported VNC query parameter")
            if name == "target" and any(value != self.target for value in request.query.getall(name)):
                raise web.HTTPForbidden(reason="VNC target is fixed by the operator")

    def _prune_handoffs(self):
        now = time.monotonic()
        self.handoffs = {
            token: record for token, record in self.handoffs.items() if record[1] > now
        }

    def _reclaim_owners(self):
        self._prune_handoffs()
        protected = set(self.tunnels) | set(self.opening) | set(self.timers)
        protected.update(owner for owner, _deadline in self.handoffs.values())
        self.owners.intersection_update(protected)

    def _owner(self, request):
        if not self.enabled:
            raise web.HTTPNotFound()
        self._require_target_query(request, handoff=request.path.endswith("/ws"))
        if not self._same_origin(request):
            raise web.HTTPForbidden(reason="Same Origin required")
        owner = request.cookies.get(COOKIE)
        if owner not in self.owners:
            raise web.HTTPUnauthorized()
        return owner

    async def info(self, request):
        self._require_target_query(request)
        origin = request.headers.get("Origin")
        if origin and not self._same_origin(request):
            raise web.HTTPForbidden(reason="Same Origin required")

        if not self.enabled:
            return web.json_response(
                {
                    "enabled": False,
                    "ws_path": "/vnc/ws",
                    "host": self.host,
                    "port": self.port,
                    "target": self.target,
                    "configured": self.configured,
                    "direct_connect": False,
                },
                headers={"Cache-Control": "no-store"},
            )

        owner = request.cookies.get(COOKIE)
        if owner not in self.owners:
            if len(self.owners) >= OWNER_LIMIT:
                self._reclaim_owners()
            if len(self.owners) >= OWNER_LIMIT:
                raise web.HTTPServiceUnavailable(reason="VNC owner limit")
            owner = secrets.token_urlsafe(32)
            self.owners.add(owner)
        tunnel = self.tunnels.get(owner)
        response = web.json_response(
            {
                "enabled": True,
                "ws_path": "/vnc/ws",
                "host": self.host,
                "port": self.port,
                "target": self.target,
                "configured": True,
                "direct_connect": False,
                "connected": bool(tunnel and tunnel.socket and not tunnel.socket.closed),
            }
        )
        response.set_cookie(
            COOKIE, owner, httponly=True, samesite="Strict", secure=request.secure
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    async def handoff(self, request):
        owner = self._owner(request)
        tunnel = self.tunnels.get(owner)
        if not tunnel or not tunnel.socket or tunnel.socket.closed:
            raise web.HTTPConflict(reason="No connected VNC client")
        self._prune_handoffs()
        # At most one usable handoff exists per owner, so a stale browser cannot
        # displace the current one after an operator asks for a new handoff.
        self.handoffs = {
            token: record for token, record in self.handoffs.items() if record[0] != owner
        }
        token = secrets.token_urlsafe(32)
        deadline = time.monotonic() + self.handoff_ttl
        self.handoffs[token] = (owner, deadline)
        return web.json_response(
            {
                "handoff": {
                    "token": token,
                    "expires_at": datetime.fromtimestamp(
                        time.time() + self.handoff_ttl, timezone.utc
                    ).isoformat(),
                }
            },
            headers={"Cache-Control": "no-store"},
        )

    async def _open_tunnel(self, owner):
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self.host,
                    self.port,
                    family=family,
                    flags=socket.AI_NUMERICHOST,
                    limit=MAX_FRAME,
                ),
                CONNECT_TIMEOUT,
            )
        except (asyncio.TimeoutError, OSError, ValueError) as error:
            raise ConnectionError("VNC upstream unavailable") from error
        tunnel = _Tunnel(owner, reader, writer)
        self.tunnels[owner] = tunnel
        tunnel.forwarder = asyncio.create_task(self._forward(tunnel))
        return tunnel

    async def _attach(self, tunnel, websocket):
        timer = self.timers.pop(tunnel.owner, None)
        if timer:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)
        if tunnel.closed:
            await websocket.close(code=1011, message=b"VNC upstream closed")
            return False
        # Serializing sends with replacement means a chunk is delivered to either
        # the old or the new browser, never discarded between the two.
        async with tunnel.lock:
            old = tunnel.socket
            tunnel.socket = None
            tunnel.attached.clear()
            if old and not old.closed:
                await old.close(code=1000, message=b"VNC handoff")
            tunnel.socket = websocket
            tunnel.attached.set()
        return True

    async def _detach(self, tunnel, websocket):
        if tunnel.closed:
            return
        detached = False
        async with tunnel.lock:
            if tunnel.socket is websocket:
                tunnel.socket = None
                tunnel.attached.clear()
                detached = True
        if detached and tunnel.owner not in self.timers:
            self.timers[tunnel.owner] = asyncio.create_task(self._expire(tunnel))

    async def _expire(self, tunnel):
        try:
            await asyncio.sleep(self.grace)
            if not tunnel.closed and tunnel.socket is None:
                await self._close_tunnel(tunnel, code=1001, message=b"VNC reconnect expired")
        finally:
            if self.timers.get(tunnel.owner) is asyncio.current_task():
                self.timers.pop(tunnel.owner, None)

    async def _forward(self, tunnel):
        try:
            while not tunnel.closed:
                data = await tunnel.reader.read(MAX_FRAME)
                if not data:
                    raise ConnectionError("VNC upstream closed")
                # Hold one bounded chunk while no browser is attached.  Not
                # reading further applies TCP backpressure to the VNC server.
                while not tunnel.closed:
                    await tunnel.attached.wait()
                    if tunnel.closed:
                        return
                    async with tunnel.lock:
                        websocket = tunnel.socket
                        if websocket is None or websocket.closed:
                            # No send was attempted, so retaining this chunk is safe.
                            # Clear the event to avoid spinning on a closed attachment.
                            tunnel.socket = None
                            tunnel.attached.clear()
                            if tunnel.owner not in self.timers:
                                self.timers[tunnel.owner] = asyncio.create_task(self._expire(tunnel))
                            continue
                        try:
                            await asyncio.wait_for(websocket.send_bytes(data), WRITE_TIMEOUT)
                            break
                        except (asyncio.TimeoutError, ConnectionError, RuntimeError) as error:
                            # A failed send may already have delivered bytes. Replaying
                            # it after reconnect can corrupt the RFB byte stream.
                            raise ConnectionError("VNC output delivery uncertain") from error
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            if not tunnel.closed:
                await self._close_tunnel(tunnel, code=1011, message=b"VNC upstream closed")

    async def _close_tunnel(self, tunnel, *, code, message):
        if tunnel.closed:
            return
        tunnel.closed = True
        tunnel.attached.set()
        if self.tunnels.get(tunnel.owner) is tunnel:
            self.tunnels.pop(tunnel.owner, None)
        timer = self.timers.pop(tunnel.owner, None)
        if timer and timer is not asyncio.current_task():
            timer.cancel()
        async with tunnel.lock:
            websocket = tunnel.socket
            tunnel.socket = None
        if websocket and not websocket.closed:
            await websocket.close(code=code, message=message)
        tunnel.writer.close()
        try:
            await asyncio.wait_for(tunnel.writer.wait_closed(), 1)
        except (asyncio.TimeoutError, OSError, ConnectionError):
            pass
        forwarder = tunnel.forwarder
        if forwarder and forwarder is not asyncio.current_task():
            forwarder.cancel()
            await asyncio.gather(forwarder, return_exceptions=True)

    async def websocket(self, request):
        owner = self._owner(request)
        token = request.query.get("handoff")
        tunnel = self.tunnels.get(owner)
        if token:
            record = self.handoffs.get(token)
            if not record or record[0] != owner or record[1] <= time.monotonic():
                raise web.HTTPForbidden(reason="Invalid handoff")
            del self.handoffs[token]  # Tokens are single-use, even if upgrade fails.
        elif tunnel and tunnel.socket and not tunnel.socket.closed:
            raise web.HTTPConflict(reason="VNC already attached; handoff required")

        websocket = web.WebSocketResponse(max_msg_size=MAX_FRAME, heartbeat=20)
        await websocket.prepare(request)
        if tunnel is None:
            if owner in self.opening:
                await websocket.close(code=1013, message=b"VNC connection in progress")
                return websocket
            self.opening.add(owner)
            try:
                tunnel = await self._open_tunnel(owner)
            except ConnectionError:
                await websocket.close(code=1011, message=b"VNC upstream unavailable")
                return websocket
            finally:
                self.opening.discard(owner)
        if not await self._attach(tunnel, websocket):
            return websocket

        try:
            async for message in websocket:
                if message.type == web.WSMsgType.BINARY:
                    if len(message.data) > MAX_FRAME:
                        await websocket.close(code=1009, message=b"VNC frame too large")
                        break
                    try:
                        tunnel.writer.write(message.data)
                        await asyncio.wait_for(tunnel.writer.drain(), WRITE_TIMEOUT)
                    except (asyncio.TimeoutError, ConnectionError, OSError):
                        await self._close_tunnel(
                            tunnel, code=1011, message=b"VNC upstream write failed"
                        )
                        break
                elif message.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSING, web.WSMsgType.CLOSED):
                    break
                else:
                    await websocket.close(code=1003, message=b"VNC requires binary frames")
                    break
        finally:
            await self._detach(tunnel, websocket)
        return websocket

    async def cleanup(self, app):
        timers = list(self.timers.values())
        for timer in timers:
            timer.cancel()
        await asyncio.gather(*timers, return_exceptions=True)
        self.timers.clear()
        await asyncio.gather(
            *(self._close_tunnel(tunnel, code=1001, message=b"VNC server shutdown")
              for tunnel in list(self.tunnels.values())),
            return_exceptions=True,
        )
        self.handoffs.clear()
        self.opening.clear()


def _environment_port(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def setup_routes(app):
    adapter = VNCAdapter(
        enabled=os.environ.get("VIBES_ENABLE_VNC", "").lower() in {"1", "true"},
        host=os.environ.get("VIBES_VNC_HOST", "127.0.0.1"),
        port=_environment_port(os.environ.get("VIBES_VNC_PORT", "5901")),
    )
    app[KEY] = adapter
    app.router.add_get("/vnc/session", adapter.info)
    app.router.add_post("/vnc/handoff", adapter.handoff)
    app.router.add_get("/vnc/ws", adapter.websocket)
    app.on_shutdown.append(adapter.cleanup)
