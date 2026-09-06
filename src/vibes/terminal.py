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
from dataclasses import dataclass, field


@dataclass
class TerminalSession:
    owner: str
    process: asyncio.subprocess.Process
    fd: int
    history: bytearray = field(default_factory=bytearray)
    clients: set = field(default_factory=set)
    closed: bool = False


class TerminalService:
    def __init__(self, cwd, shell="/bin/sh", history_limit=65536):
        self.cwd = cwd
        self.shell = shell
        self.history_limit = history_limit
        self.sessions = {}
        self.lock = asyncio.Lock()

    async def open(self, owner):
        if not owner:
            raise ValueError("Terminal owner required")
        async with self.lock:
            existing = self.sessions.get(owner)
            if existing and not existing.closed:
                return existing
            master, slave = pty.openpty()
            try:
                process = await asyncio.create_subprocess_exec(
                    self.shell, "-i", stdin=slave, stdout=slave, stderr=slave,
                    cwd=self.cwd, env={**os.environ, "TERM": "xterm-256color"},
                    start_new_session=True,
                )
            except BaseException:
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

    async def close(self, session):
        if session.closed:
            return
        session.closed = True
        asyncio.get_running_loop().remove_reader(session.fd)
        os.close(session.fd)
        try:
            os.killpg(session.process.pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(session.process.wait(), 2)
        except asyncio.TimeoutError:
            try:
                os.killpg(session.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await session.process.wait()
        session.clients.clear()
        if self.sessions.get(session.owner) is session:
            del self.sessions[session.owner]

    async def shutdown(self):
        for session in tuple(self.sessions.values()):
            await self.close(session)
