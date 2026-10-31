"""Shell detection: the configured shell path wins, otherwise the documented candidates are tried."""

import os
import shutil
from pathlib import Path

POSIX_CANDIDATES = ('$SHELL', '/bin/bash', 'bash on PATH')
WINDOWS_CANDIDATES = (
    '$SHELL',
    'C:\\Program Files\\PowerShell\\7\\pwsh.exe',
    'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe',
    'pwsh.exe',
    'powershell.exe',
    '%ComSpec%',
    'cmd.exe',
)


def shell_argv(shell_path: str, kind: str, command: str) -> list[str]:
    if kind == 'powershell':
        return [shell_path, '-NoProfile', '-Command', command]
    if kind == 'cmd':
        return [shell_path, '/c', command]
    return [shell_path, '-c', command]


def detect_shell(shell_path: str | None = None, env=None, platform: str | None = None,
                can_start=None) -> dict:
    """Return {path, kind, argv(command)}; raises naming every candidate that was tried."""
    env = dict(env if env is not None else os.environ)
    platform = (platform or ('windows' if os.name == 'nt' else 'posix')).lower()
    windows = platform.startswith(('windows', 'win32'))
    tried: list[str] = []

    def usable(path: str, kind: str) -> bool:
        if not path:
            return False
        if not Path(path).is_file():
            return False
        if can_start is None:
            return os.access(path, os.X_OK)
        return can_start(path)

    configured = (shell_path or '').strip()
    if configured:
        # A configured shell path wins and is run as a POSIX shell even on Windows (e.g. Git Bash).
        tried.append(configured)
        if usable(configured, 'posix'):
            return {'path': configured, 'kind': 'posix', 'argv': lambda command: shell_argv(configured, 'posix', command)}
        raise FileNotFoundError(f'Shell not found: {configured}')

    candidates = WINDOWS_CANDIDATES if windows else POSIX_CANDIDATES
    for candidate in candidates:
        if candidate == '$SHELL':
            path = env.get('SHELL', '')
            kind = 'posix'
        elif candidate == 'bash on PATH':
            path = shutil.which('bash') or ''
            kind = 'posix'
        elif candidate == '%ComSpec%':
            path = env.get('ComSpec', '')
            kind = 'cmd'
        else:
            path = candidate if windows and Path(candidate).is_absolute() else (shutil.which(candidate) or '')
            kind = ('powershell' if 'powershell' in Path(path).name.lower() or 'pwsh' in Path(path).name.lower()
                    else 'cmd') if windows else 'posix'
        if not path:
            tried.append(candidate)
            continue
        tried.append(path)
        if usable(path, kind):
            return {'path': path, 'kind': kind, 'argv': lambda command, path=path, kind=kind: shell_argv(path, kind, command)}

    raise FileNotFoundError('No usable shell: ' + ', '.join(tried))
