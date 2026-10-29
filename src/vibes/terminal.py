"""Local Unix PTY lifecycle, independent of HTTP transport.

Owners are established by the HTTP adapter, never by input control frames.
"""
import asyncio
import errno
import fcntl
import os
import pty
import signal
import struct
import termios
import sys
import secrets
from datetime import datetime, timezone
from dataclasses import dataclass, field

from .secure.environment_overrides import PRIVATE_VARIABLES


async def _settle(task):
    """Join owned cleanup/acquisition despite repeated waiter cancellation."""
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done():
                return task.result()


@dataclass
class TerminalSession:
    owner: str
    process: asyncio.subprocess.Process
    fd: int
    history: bytearray = field(default_factory=bytearray)
    clients: set = field(default_factory=set)
    closed: bool = False
    close_task: asyncio.Task | None = None
    session_id: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TerminalService:
    def __init__(self, cwd, shell="/bin/sh", history_limit=65536):
        self.cwd = cwd
        self.shell = shell
        self.history_limit = history_limit
        self.sessions = {}
        self.lock = asyncio.Lock()
        self.closing = False

    async def open(self, owner):
        if not owner:
            raise ValueError("Terminal owner required")
        async with self.lock:
            if self.closing:
                raise RuntimeError('Terminal service is shutting down')
            existing = self.sessions.get(owner)
            if existing and not existing.closed and existing.process.returncode is None:
                return existing
            if existing:
                await self.close(existing)
            master, slave = pty.openpty()
            spawn = None
            try:
                spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                    # Establish the controlling terminal after setsid, without
                    # preexec_fn (unsafe in a threaded server process).
                    sys.executable, "-c",
                    "import fcntl,os,sys,termios; "
                    "fcntl.ioctl(0,termios.TIOCSCTTY,0); "
                    "os.execv(sys.argv[1],[sys.argv[1],'-i'])",
                    self.shell, stdin=slave, stdout=slave, stderr=slave,
                    cwd=self.cwd, env={
                        **{name: value for name, value in os.environ.items() if name not in PRIVATE_VARIABLES},
                        "TERM": "xterm-256color",
                    },
                    start_new_session=True,
                ))
                process = await asyncio.shield(spawn)
            except BaseException:
                # Spawn can complete after its waiter is cancelled. Retain the
                # task and slave fd until acquisition settles, then reap it.
                try:
                    if spawn is not None:
                        try:
                            process = await _settle(spawn)
                        except BaseException:
                            pass
                        else:
                            await _settle(asyncio.create_task(self._reap(process)))
                finally:
                    os.close(master)
                raise
            finally:
                os.close(slave)
            os.set_blocking(master, False)
            session = TerminalSession(owner, process, master)
            self.sessions[owner] = session
            asyncio.get_running_loop().add_reader(master, self._read, session)
            return session

    def _read(self, session):
        try:
            output = os.read(session.fd, 4096)
        except BlockingIOError:
            return
        except OSError as exc:
            if exc.errno != errno.EIO:
                raise
            output = b""
        if not output:
            asyncio.get_running_loop().remove_reader(session.fd)
            return
        session.history.extend(output)
        del session.history[:max(0, len(session.history) - self.history_limit)]
        for client in tuple(session.clients):
            try:
                client.put_nowait(output)
            except asyncio.QueueFull:
                # A slow subscriber must not block the PTY or grow memory.
                session.clients.discard(client)

    async def write(self, session, data):
        if session.closed:
            raise ValueError("Terminal is closed")
        if len(data) > 65536:
            raise ValueError("Terminal input exceeds limit")
        view = memoryview(data)
        while view:
            try:
                count = os.write(session.fd, view)
                view = view[count:]
            except BlockingIOError:
                await asyncio.sleep(0.01)

    def resize(self, session, cols, rows):
        if session.closed:
            raise ValueError("Terminal is closed")
        cols = max(20, min(400, int(cols)))
        rows = max(5, min(200, int(rows)))
        fcntl.ioctl(session.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        try:
            os.killpg(session.process.pid, signal.SIGWINCH)
        except ProcessLookupError:
            pass

    async def _reap(self, process):
        try:
            os.killpg(process.pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.wait(), 2)
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()

    async def close(self, session):
        if session.close_task is None:
            session.closed = True
            asyncio.get_running_loop().remove_reader(session.fd)
            os.close(session.fd)
            session.close_task = asyncio.create_task(self._finish_close(session))
        try:
            await asyncio.shield(session.close_task)
        except asyncio.CancelledError:
            await _settle(session.close_task)
            raise

    async def _finish_close(self, session):
        await self._reap(session.process)
        session.clients.clear()
        if self.sessions.get(session.owner) is session:
            del self.sessions[session.owner]

    async def shutdown(self):
        self.closing = True
        async with self.lock:
            for session in tuple(self.sessions.values()):
                await self.close(session)
