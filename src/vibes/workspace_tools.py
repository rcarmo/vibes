"""Read-only workspace references with descriptor-relative, no-symlink traversal."""
import os
import stat
from pathlib import Path


class WorkspaceTools:
    def __init__(self, root):
        self.root = str(Path(root).resolve(strict=True))

    def list_directory(self, path: str = '.', limit: int = 100):
        if not isinstance(path, str) or not path or path.startswith('/'):
            raise ValueError('A relative workspace directory is required')
        parts = [] if path == '.' else path.split('/')
        if any(part in {'', '.', '..'} for part in parts):
            raise ValueError('Invalid workspace path')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('limit must be between 1 and 200')
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            entries = []
            more = False
            # Iterate at most limit+1 entries, rather than sorting an unbounded directory.
            with os.scandir(fd) as iterator:
                for entry in iterator:
                    if len(entries) == limit:
                        more = True
                        break
                    kind = 'symlink' if entry.is_symlink() else 'directory' if entry.is_dir(follow_symlinks=False) else 'file' if entry.is_file(follow_symlinks=False) else 'special'
                    entries.append({'name': entry.name, 'type': kind})
            return {'path': path, 'entries': entries, 'truncated': more}
        finally:
            os.close(fd)

    def read(self, path: str, offset: int = 0, limit: int = 24000):
        if not isinstance(path, str) or not path or path.startswith('/'):
            raise ValueError('A relative workspace path is required')
        parts = path.split('/')
        if any(part in {'', '.', '..'} for part in parts):
            raise ValueError('Invalid workspace path')
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 24000:
            raise ValueError('Invalid byte range')
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for index, part in enumerate(parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if index < len(parts) - 1:
                    flags |= os.O_DIRECTORY
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('Only regular files can be read')
            data = os.pread(fd, limit, offset)
            if b'\0' in data:
                raise ValueError('Binary file: text preview unavailable')
            return {'path': path, 'text': data.decode('utf-8', errors='replace'),
                'offset': offset, 'next_offset': offset + len(data),
                'size': info.st_size, 'has_more': offset + len(data) < info.st_size}
        finally:
            os.close(fd)
