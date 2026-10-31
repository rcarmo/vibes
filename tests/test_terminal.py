"""Real POSIX PTY tests; HTTP terminal access is separately opt-in."""
import asyncio
import importlib
import struct

import pytest
termios = pytest.importorskip('termios', reason='POSIX PTY module; Windows terminal is explicitly disabled')
fcntl = pytest.importorskip('fcntl', reason='POSIX PTY module; Windows terminal is explicitly disabled')

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
async def test_terminal_environment_excludes_server_keychain_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv('VIBES_KEYCHAIN_MASTER_PASSWORD', 'synthetic-private-master')
    monkeypatch.setenv('VIBES_KEYCHAIN_KEY_PATH', '/synthetic/private/key')
    service = TerminalService(str(tmp_path))
    session = await service.open('environment')
    try:
        await service.write(session, b'printf "private-vars:%s:%s\\n" "${VIBES_KEYCHAIN_MASTER_PASSWORD-unset}" "${VIBES_KEYCHAIN_KEY_PATH-unset}"\n')
        async with asyncio.timeout(3):
            while b'private-vars:unset:unset' not in session.history:
                await asyncio.sleep(.02)
        assert b'synthetic-private-master' not in session.history
        assert b'/synthetic/private/key' not in session.history
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
