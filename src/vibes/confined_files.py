"""Bounded workspace reads without following links, including Windows reparse points.

Windows holds every ancestor open without delete sharing until the file is read.
The final file is opened without write/delete sharing. No process-global cwd change.
UNC/device paths, ADS, ambiguous DOS names and drive-relative paths are rejected.
"""
import os
import stat
from pathlib import Path


def relative_parts(root, value):
    if not isinstance(value, str) or not value or len(value) > 4096 or '\x00' in value:
        raise ValueError('A workspace file path is required')
    value = value.removeprefix('@')
    if os.name == 'nt':
        import ntpath
        value = value.replace('\\', '/')
        if value.startswith('//'):
            raise ValueError('UNC and device paths are not supported')
        drive, tail = ntpath.splitdrive(value)
        if drive:
            if not tail.startswith('/'):
                raise ValueError('Drive-relative paths are not supported')
            # Check the original spelling before normalising, including dot segments.
            check = tail.lstrip('/').split('/')
        else:
            if value.startswith('/'):
                raise ValueError('Root-relative paths are not supported')
            check = value.split('/')
        reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} | {f'{p}{n}' for p in ('COM', 'LPT') for n in range(1, 10)}
        for part in check:
            if (not part or part in {'.', '..'} or part.endswith((' ', '.'))
                    or any(ord(c) < 32 or c in ':<>"|?*' for c in part)
                    or part.split('.')[0].upper() in reserved):
                raise ValueError('Invalid workspace path')
        candidate = Path(value)
    else:
        candidate = Path(value)
        check = value.lstrip('/').split('/') if candidate.is_absolute() else value.split('/')
        if any(part in ('', '.', '..') for part in check):
            raise ValueError('Invalid workspace path')
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(root)
        except ValueError:
            raise ValueError('Attachment must be inside the workspace') from None
    parts = candidate.parts
    if not parts or any(p in ('', '.', '..') for p in parts):
        raise ValueError('Invalid workspace path')
    return parts


def read_bytes(root, path, max_bytes):
    root = Path(root).absolute()  # Do not resolve away a symlink/reparse point.
    parts = relative_parts(root, path)
    if os.name == 'nt':
        data = _read_windows(root, parts, max_bytes)
    else:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
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
                raise ValueError('Only regular files can be attached')
            if info.st_size > max_bytes:
                raise ValueError('Attachment exceeds size limit')
            with os.fdopen(os.dup(fd), 'rb') as file:
                data = file.read(max_bytes + 1)
        finally:
            os.close(fd)
    if len(data) > max_bytes:
        raise ValueError('Attachment exceeds size limit')
    return parts[-1], data


def _read_windows(root, parts, max_bytes):
    import ctypes
    from ctypes import wintypes as w
    import msvcrt

    class FileInfo(ctypes.Structure):
        _fields_ = [('attributes', w.DWORD), ('created', w.FILETIME), ('accessed', w.FILETIME),
                    ('written', w.FILETIME), ('volume', w.DWORD), ('size_high', w.DWORD),
                    ('size_low', w.DWORD), ('links', w.DWORD), ('index_high', w.DWORD), ('index_low', w.DWORD)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.GetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.POINTER(FileInfo)]
    kernel.GetFileInformationByHandle.restype = w.BOOL
    kernel.GetFileType.argtypes = [w.HANDLE]
    kernel.GetFileType.restype = w.DWORD
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    if not root.drive or len(root.drive) != 2 or root.drive[1] != ':':
        raise ValueError('Workspace must be on a local drive')
    handles = []
    invalid = ctypes.c_void_p(-1).value

    def acquire(path, directory):
        # BACKUP_SEMANTICS permits directory handles; OPEN_REPARSE_POINT prevents traversal.
        h = kernel.CreateFileW(str(path), 0x80 if directory else 0x80000000,
                               1, None, 3, 0x02200000, None)
        if h == invalid:
            raise ctypes.WinError(ctypes.get_last_error())
        handles.append(h)
        info = FileInfo()
        if not kernel.GetFileInformationByHandle(h, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & 0x400:
            raise ValueError('Links and reparse points are not allowed')
        if bool(info.attributes & 0x10) != directory or kernel.GetFileType(h) != 1:
            raise ValueError('Only regular workspace files/directories are allowed')
        return h, info

    try:
        current = Path(root.anchor)
        acquire(current, True)
        for part in (*root.parts[1:], *parts[:-1]):
            current = current / part
            acquire(current, True)
        h, info = acquire(current / parts[-1], False)
        if (info.size_high << 32) | info.size_low > max_bytes:
            raise ValueError('Attachment exceeds size limit')
        # Transfer ownership to the CRT; all ancestor handles remain locked.
        fd = msvcrt.open_osfhandle(h, os.O_RDONLY | os.O_BINARY)
        handles.pop()
        with os.fdopen(fd, 'rb') as file:
            return file.read(max_bytes + 1)
    finally:
        for h in reversed(handles):
            kernel.CloseHandle(h)
