"""Explicit read-only workspace notes; never auto-discover or write memory."""
from pathlib import Path


def load_workspace_memory(root, paths, *, max_bytes=24000):
    root = Path(root).resolve()
    if not isinstance(paths, list) or len(paths) > 16 or not 1 <= max_bytes <= 64000:
        raise ValueError('Invalid memory bounds')
    remaining = max_bytes
    sources, diagnostics = [], []
    for name in dict.fromkeys(paths):
        if not isinstance(name, str) or Path(name).is_absolute():
            raise ValueError('Memory paths must be workspace-relative')
        path = (root / name).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() != '.md':
            raise ValueError('Memory must be confined workspace Markdown')
        if not path.is_file():
            diagnostics.append({'path': name, 'status': 'missing'})
            continue
        with path.open('rb') as source:
            data = source.read(remaining + 1)
        if len(data) > remaining:
            diagnostics.append({'path': name, 'status': 'over-budget'})
            continue
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            diagnostics.append({'path': name, 'status': 'invalid-utf8'})
            continue
        remaining -= len(data)
        sources.append({'path': str(path.relative_to(root)), 'text': text, 'bytes': len(data)})
    return {'sources': sources, 'diagnostics': diagnostics, 'bytes': max_bytes - remaining}
