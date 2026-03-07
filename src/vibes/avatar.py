"""Avatar caching service for Vibes.

Fetches external avatar URLs and caches them locally so the frontend can
display them without CORS issues.  Avatars are stored in .vibes/avatars/.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from pathlib import Path
from typing import Optional
import urllib.request

logger = logging.getLogger(__name__)

AVATAR_DIR = Path(".vibes") / "avatars"

ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/x-icon",
    "image/vnd.microsoft.icon",
}

META_KEYS = ("source", "file", "content_type", "updated_at")


def _meta_path(kind: str) -> Path:
    return AVATAR_DIR / f"{kind}.json"


def _read_meta(kind: str) -> Optional[dict]:
    path = _meta_path(kind)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data if all(k in data for k in META_KEYS) else None
    except Exception:
        return None


def _write_meta(kind: str, meta: dict) -> None:
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    _meta_path(kind).write_text(json.dumps(meta, indent=2))


def _guess_extension(content_type: str, url: str) -> str:
    ext = mimetypes.guess_extension(content_type or "")
    if ext and ext != ".bin":
        if ext == ".jpe":
            ext = ".jpg"
        return ext
    # Fall back to URL path extension
    suffix = Path(url.split("?")[0].split("#")[0]).suffix.lower()
    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"):
        return suffix
    return ".png"


def _normalise_content_type(ct: str) -> str:
    ct = (ct or "").split(";")[0].strip().lower()
    return ct if ct in ALLOWED_CONTENT_TYPES else ""


async def ensure_avatar_cache(kind: str, source: str) -> Optional[dict]:
    """Fetch an external avatar URL and cache it locally.

    Returns the metadata dict with keys (source, file, content_type,
    updated_at) or None if fetching failed.
    """
    source = (source or "").strip()
    if not source:
        return None

    # Check existing cache
    existing = _read_meta(kind)
    if existing and existing["source"] == source and Path(existing["file"]).exists():
        return existing

    # Fetch the image
    try:
        loop = asyncio.get_event_loop()
        req = urllib.request.Request(source, headers={"User-Agent": "vibes"})
        resp = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=15)
        )
        data = resp.read()
        raw_ct = resp.headers.get("Content-Type", "")
    except Exception as e:
        logger.warning("Failed to fetch avatar from %s: %s", source, e)
        return None

    if not data:
        return None

    content_type = _normalise_content_type(raw_ct)
    if not content_type:
        # Try to guess from URL extension
        suffix = Path(source.split("?")[0]).suffix.lower()
        guessed = mimetypes.guess_type(f"file{suffix}")[0] or ""
        content_type = _normalise_content_type(guessed) or "image/png"

    ext = _guess_extension(content_type, source)
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    file_path = AVATAR_DIR / f"{kind}{ext}"

    # Clean up old file if extension changed
    if existing and existing.get("file") and existing["file"] != str(file_path):
        old = Path(existing["file"])
        if old.exists():
            old.unlink(missing_ok=True)

    file_path.write_bytes(data)

    from datetime import datetime, timezone

    meta = {
        "source": source,
        "file": str(file_path),
        "content_type": content_type,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_meta(kind, meta)
    logger.info("Cached %s avatar from %s (%s)", kind, source, content_type)
    return meta


def clear_avatar_cache(kind: str) -> None:
    """Remove cached avatar for a given kind."""
    meta = _read_meta(kind)
    if meta and meta.get("file"):
        p = Path(meta["file"])
        if p.exists():
            p.unlink(missing_ok=True)
    mp = _meta_path(kind)
    if mp.exists():
        mp.unlink(missing_ok=True)


def resolve_avatar_url(kind: str, source: Optional[str] = None) -> Optional[str]:
    """Return the local serving path for a cached avatar, or None."""
    if not source:
        return None
    meta = _read_meta(kind)
    if meta and meta["source"] == source and Path(meta["file"]).exists():
        return f"/avatar/{kind}"
    # Not cached yet — still return the path; the route handler will
    # trigger caching on first request.
    return f"/avatar/{kind}"
