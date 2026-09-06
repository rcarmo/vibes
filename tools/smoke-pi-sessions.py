"""Verify installed Pi session switching without prompts or model calls.

Run: PYTHONPATH=src .venv/bin/python tools/smoke-pi-sessions.py
"""
import asyncio
import json
import shutil
import tempfile

from vibes.pi_sessions import PiSessionSelector


async def main():
    executable = shutil.which('pi')
    if not executable:
        raise RuntimeError('pi executable not found')
    with tempfile.TemporaryDirectory(prefix='vibes-pi-sessions-') as directory:
        process = await asyncio.create_subprocess_exec(executable, '--mode', 'rpc',
            '--session-dir', directory, '--no-extensions', cwd=directory,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        sequence = 0

        async def rpc(command):
            nonlocal sequence
            sequence += 1
            request_id = str(sequence)
            process.stdin.write((json.dumps({**command, 'id': request_id}) + '\n').encode())
            await process.stdin.drain()
            async with asyncio.timeout(15):
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        raise RuntimeError('Pi exited before responding')
                    event = json.loads(line)
                    if event.get('id') == request_id:
                        return event
        try:
            selector = PiSessionSelector()
            original = await selector.select('default', rpc)
            other = await selector.select('other', rpc)
            restored = await selector.select('default', rpc)
            if not original or original == other or restored != original:
                raise RuntimeError('Session isolation or restoration failed')
            print('PASS: distinct Pi session created and original restored; no model prompt sent.')
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()


if __name__ == '__main__':
    asyncio.run(main())
