"""Workspace files delivered as durable, session-owned timeline messages.

Only the running turn can publish; trusted Pi/ACP adapters hold opaque transport
capabilities. Neither a tool parameter nor a browser chooses the destination.
"""
import asyncio
import hashlib
import io
import json
import mimetypes
import os
import re
from pathlib import Path
import secrets
import stat

from PIL import Image

from .db import get_db
from .routes.media import generate_thumbnail

MAX_BYTES = 10 * 1024 * 1024
SAFE_IMAGES = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'GIF': 'image/gif', 'WEBP': 'image/webp', 'AVIF': 'image/avif'}
PI_TOKEN = secrets.token_urlsafe(32)
_acp_tokens = {}
active = None
publish_lock = asyncio.Lock()


def acp_token(session_id):
    # One capability per known ACP conversation, retained across its turns.
    return _acp_tokens.setdefault(session_id, secrets.token_urlsafe(32))


def resolve_token(token):
    if secrets.compare_digest(token, PI_TOKEN):
        return 'pi', None
    for session_id, capability in _acp_tokens.items():
        if secrets.compare_digest(token, capability):
            return 'acp', session_id
    raise PermissionError('Attachment capability is invalid')


def read_attachment_file(root, path, name=None, content_type=None, kind=None, max_bytes=MAX_BYTES):
    if not isinstance(path, str) or not path or len(path) > 4096:
        raise ValueError('A workspace file path is required')
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ValueError('max_bytes must be between 1 and 10485760')
    if kind not in (None, 'image', 'file'):
        raise ValueError('kind must be image or file')
    root = Path(root).resolve(strict=True)
    path = path.removeprefix('@')
    if Path(path).is_absolute():
        try:
            path = str(Path(path).relative_to(root))
        except ValueError:
            raise ValueError('Attachment must be inside the workspace') from None
    parts = path.split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise ValueError('Invalid workspace path')
    filename = name or parts[-1]
    if not isinstance(filename, str) or not filename or len(filename) > 255 or any(ord(c) < 32 or c in '/\\' for c in filename):
        raise ValueError('Invalid attachment name')
    if content_type is not None and (not isinstance(content_type, str) or len(content_type) > 100 or '/' not in content_type or any(c.isspace() for c in content_type)):
        raise ValueError('Invalid MIME type')
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
        if len(data) > max_bytes:
            raise ValueError('Attachment exceeds size limit')
    finally:
        os.close(fd)
    mime = content_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    metadata = {'size': len(data), 'source': 'agent-attachment'}
    # Sniff and validate raster images; do not label arbitrary bytes as images.
    try:
        with Image.open(io.BytesIO(data)) as image:
            detected = SAFE_IMAGES.get(image.format)
            if image.width * image.height > 40_000_000:
                raise ValueError('Image exceeds pixel limit')
            image.verify()
            if detected:
                mime = detected
                metadata.update(width=image.width, height=image.height)
    except (OSError, SyntaxError, Image.DecompressionBombError):
        if kind == 'image' or mime.startswith('image/') and mime != 'image/svg+xml':
            raise ValueError('Invalid or unsupported image; attach as a file with its actual MIME type') from None
        detected = None
    if kind == 'image' and not detected:
        raise ValueError('Inline images must be PNG, JPEG, GIF, WebP or AVIF')
    actual_kind = 'file' if kind == 'file' or not detected else 'image'
    if actual_kind == 'file' and mime.startswith('image/'):
        # Force a download even when the source is a raster image.
        metadata['original_content_type'] = mime
        mime = 'application/octet-stream'
    metadata['kind'] = actual_kind
    thumbnail = generate_thumbnail(data, mime) if actual_kind == 'image' else None
    return filename, mime, data, thumbnail, metadata


async def referenced_media(content, session_id):
    """Resolve only numeric references already published in this conversation."""
    database = await get_db()
    ids = list(dict.fromkeys(int(value) for value in re.findall(r'attachment:(\d+)\b', content or '')))[:50]
    result = []
    for media_id in ids:
        async with database._connection.execute('''SELECT 1 FROM interactions i, json_each(i.data, '$.media_ids') m
            WHERE m.value=? AND COALESCE(json_extract(i.data, '$.session_id'), 'default')=? LIMIT 1''', (media_id, session_id)) as cursor:
            if not await cursor.fetchone():
                continue
        record = await database.get_media(media_id)
        if record:
            result.append({'type': 'image' if record['content_type'] in SAFE_IMAGES.values() else 'file',
                           'media_id': media_id, 'name': record['filename'], 'content_type': record['content_type']})
    return result


async def publish_file(params, mode, session_id=None, *, expected=None):
    from .routes.sse import broadcast_event
    context = active
    if not context or context['mode'] != mode or session_id is not None and context['session_id'] != session_id:
        raise PermissionError('No matching active agent turn')
    if expected is not None and context is not expected:
        raise PermissionError('Agent turn changed')
    request_id = params.get('request_id')
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 200:
        raise ValueError('A bounded request_id is required')
    allowed = {'path', 'name', 'content_type', 'kind', 'max_bytes', 'request_id'}
    if set(params) - allowed:
        raise ValueError('Unsupported attachment fields')
    fingerprint = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    async with publish_lock:
        if active is not context:
            raise PermissionError('Agent turn ended')
        if len(context['receipts']) >= 100 and request_id not in context['receipts']:
            raise ValueError('Attachment limit reached for this turn')
        existing = context['receipts'].get(request_id)
        if existing:
            if existing[0] != fingerprint:
                raise ValueError('request_id already used with different parameters')
            return existing[1]
        filename, mime, data, thumbnail, metadata = await asyncio.to_thread(
            read_attachment_file, Path.cwd(), **{key: value for key, value in params.items() if key != 'request_id'})
        if active is not context:
            raise PermissionError('Agent turn ended before attachment was stored')
        database = await get_db()
        media_id = await database.create_media(filename, mime, data, thumbnail, metadata)
        try:
            if active is not context:
                raise PermissionError('Agent turn ended before delivery')
            row = {'type': 'agent_response', 'content': '', 'agent_id': context['agent_id'],
                   'thread_id': context['thread_id'], 'session_id': context['session_id'],
                   'turn_id': context['turn_id'], 'intermediate': True,
                   'media_ids': [media_id], 'content_blocks': [{'type': metadata['kind'], 'media_id': media_id,
                   'name': filename, 'content_type': mime}], 'attachment_request_id': request_id}
            row_id = await database.create_interaction(row)
        except BaseException:
            await database.delete_media([media_id])
            raise
        result = {'media_id': media_id, 'message_id': row_id, 'session_id': context['session_id'],
                  'name': filename, 'content_type': mime, 'kind': metadata['kind'], 'size': len(data),
                  'reference': f'attachment:{media_id}', 'url': f'/media/{media_id}',
                  'text': f'Attached {filename}. It is already visible in the timeline; no base64 or final-response copy is needed.'}
        context['receipts'][request_id] = (fingerprint, result)
        # new_post delivers an assistant-owned row without signalling turn end.
        await broadcast_event('new_post', await database.get_interaction(row_id))
        await broadcast_event('sessions_changed', {'session_id': context['session_id']})
        return result
