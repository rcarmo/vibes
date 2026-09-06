"""Real PTY tests; no HTTP route enables terminal access yet."""
import asyncio
import importlib
import struct
import termios
import fcntl

import pytest

TerminalService = importlib.import_module("vibes.terminal").TerminalService


@pytest.mark.asyncio
async def test_terminal_output_resize_reuse_and_cleanup(tmp_path):
    service = TerminalService(str(tmp_path))
    session = await service.open("owner")
    try:
        assert await service.open("owner") is session
        await service.write(session, b"printf 'parity-%s\\n' verified\n")
        async with asyncio.timeout(5):
            while b"parity-verified" not in session.history:
                await asyncio.sleep(0.02)
        service.resize(session, 100, 30)
        rows, cols, _, _ = struct.unpack("HHHH", fcntl.ioctl(session.fd, termios.TIOCGWINSZ, b"\0" * 8))
        assert (cols, rows) == (100, 30)
    finally:
        await service.shutdown()
    assert session.closed
    assert session.process.returncode is not None
    assert not service.sessions


@pytest.mark.asyncio
async def test_owner_isolation_and_input_limit(tmp_path):
    service = TerminalService(str(tmp_path), history_limit=64)
    first = await service.open("first")
    second = await service.open("second")
    try:
        assert first is not second
        with pytest.raises(ValueError):
            await service.write(first, b"x" * 65537)
        await service.write(first, b"printf '%0100d' 1\n")
        await asyncio.sleep(0.1)
        assert len(first.history) <= 64
        with pytest.raises(ValueError):
            await service.open("")
    finally:
        await service.shutdown()


@pytest.mark.asyncio
async def test_controlling_terminal_and_foreground_interrupt(tmp_path):
    service = TerminalService(str(tmp_path))
    session = await service.open('job-control')
    try:
        await service.write(session, b"test -r /dev/tty && printf 'tty-%s\\n' ready\n")
        async with asyncio.timeout(3):
            while b'tty-ready' not in session.history:
                await asyncio.sleep(0.02)
        assert b'no job control' not in session.history
        await service.write(session, b"sleep 30\n")
        await asyncio.sleep(0.1)
        await service.write(session, b'\x03')
        await service.write(session, b"printf 'interrupt-%s\\n' survived\n")
        async with asyncio.timeout(3):
            while b'interrupt-survived' not in session.history:
                await asyncio.sleep(0.02)
    finally:
        await service.shutdown()
