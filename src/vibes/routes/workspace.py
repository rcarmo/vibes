"""Workspace manager routes for tree browsing and file previews."""

from __future__ import annotations

import asyncio
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from threading import Event

from aiohttp import web

from ..db import get_db
from .sse import broadcast_event

try:
    from watchfiles import awatch
except ImportError:  # pragma: no cover - fallback path for constrained installs
    awatch = None

DEFAULT_TREE_DEPTH = 2
MAX_TREE_DEPTH = 6
DEFAULT_PREVIEW_BYTES = 20_000
MAX_PREVIEW_BYTES = 500_000
MAX_FILE_WRITE_BYTES = 5_000_000
MAX_TREE_ENTRIES = 2_000
TEXT_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".html", ".css", ".xml", ".sh",
}
EXCLUDE_DIRS = {
    "node_modules", ".git", "dist", "build", "output", ".cache", ".venv", "tmp", "coverage",
}

_workspace_visible = False
_workspace_show_hidden = False
_workspace_last_signature: str | None = None
_workspace_poll_task: asyncio.Task | None = None
_workspace_watch_stop_event: Event | None = None
_workspace_poll_lock = asyncio.Lock()
_workspace_poll_interval_s = 1.0
_workspace_watch_debounce_ms = 300
_workspace_watch_step_ms = 50
_workspace_update_throttle_s = 1.0
_workspace_pending_updates: dict[str, dict] = {}
_workspace_throttle_task: asyncio.Task | None = None
_workspace_last_emit_at = 0.0


def _workspace_root() -> Path:
    return Path.cwd().resolve()


def _is_within_workspace(path: Path) -> bool:
    root = _workspace_root()
    return path == root or root in path.parents


def _is_hidden_relative(rel_path: Path) -> bool:
    parts = [p for p in rel_path.parts if p not in ("", ".")]
    return any(part.startswith(".") for part in parts)


def _is_excluded_relative(rel_path: Path) -> bool:
    parts = [p for p in rel_path.parts if p not in ("", ".")]
    return any(part in EXCLUDE_DIRS for part in parts)


def _to_workspace_relative(path: Path) -> str:
    root = _workspace_root()
    if path == root:
        return "."
    return path.relative_to(root).as_posix()


def _resolve_workspace_path(path_value: str | None) -> Path:
    root = _workspace_root()
    candidate = root if not path_value or path_value in ("", ".") else (root / path_value).resolve()
    if candidate != root and root not in candidate.parents:
        raise web.HTTPForbidden(text=json.dumps({"error": "Path is outside workspace"}), content_type="application/json")
    return candidate


def _node_signature(node: dict) -> str:
    return json.dumps(node, sort_keys=True, separators=(",", ":"))


def _format_mtime(path: Path) -> str:
    stat = path.stat()
    return datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()


def _build_tree(path: Path, depth: int, show_hidden: bool, state: dict[str, int | bool]) -> dict:
    state["count"] = int(state["count"]) + 1
    if int(state["count"]) > MAX_TREE_ENTRIES:
        state["truncated"] = True
        return {
            "name": "." if path == _workspace_root() else path.name,
            "path": _to_workspace_relative(path),
            "type": "dir" if path.is_dir() else "file",
            "children": [],
        }

    rel_path = _to_workspace_relative(path)
    node = {
        "name": "." if rel_path == "." else path.name,
        "path": rel_path,
        "type": "dir" if path.is_dir() else "file",
    }

    if not path.is_dir():
        return node

    if depth <= 0:
        node["children"] = []
        return node

    children: list[dict] = []
    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        node["children"] = []
        return node

    for entry in entries:
        try:
            rel = entry.relative_to(_workspace_root())
        except ValueError:
            continue
        if _is_excluded_relative(rel):
            continue
        if not show_hidden and _is_hidden_relative(rel):
            continue
        if int(state["count"]) >= MAX_TREE_ENTRIES:
            state["truncated"] = True
            break
        children.append(_build_tree(entry, depth - 1, show_hidden, state))

    node["children"] = children
    return node


def _is_text_file(path: Path, content_type: str | None) -> bool:
    if content_type and content_type.startswith("text/"):
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


async def _broadcast_workspace_tree_if_changed(force: bool = False) -> None:
    global _workspace_last_signature, _workspace_last_emit_at
    root = _workspace_root()
    state: dict[str, int | bool] = {"count": 0, "truncated": False}
    tree = _build_tree(root, depth=4, show_hidden=_workspace_show_hidden, state=state)
    update = {
        "path": ".",
        "root": tree,
        "truncated": bool(state["truncated"]),
    }
    signature = _node_signature(update)
    if not force and _workspace_last_signature == signature:
        return
    _workspace_last_signature = signature
    _workspace_last_emit_at = asyncio.get_running_loop().time()
    await broadcast_event("workspace_update", {"updates": [update]})


async def _workspace_poll_loop() -> None:
    try:
        while _workspace_visible:
            await _broadcast_workspace_tree_if_changed()
            await asyncio.sleep(_workspace_poll_interval_s)
    except asyncio.CancelledError:
        raise


def _compress_paths(paths: list[str]) -> list[str]:
    normalized = sorted(set((p or ".").replace("\\", "/") for p in paths), key=len)
    if "." in normalized:
        return ["."]
    filtered: list[str] = []
    existing = set(normalized)
    for candidate in normalized:
        current = candidate
        keep = True
        while "/" in current:
            current = current.rsplit("/", 1)[0]
            if current in existing:
                keep = False
                break
        if keep:
            filtered.append(candidate)
    return filtered


def _build_workspace_update(path_value: str) -> dict | None:
    try:
        target = _resolve_workspace_path(path_value)
    except web.HTTPForbidden:
        return None
    if not target.exists():
        return None
    depth = 4 if path_value == "." else 3
    state: dict[str, int | bool] = {"count": 0, "truncated": False}
    tree = _build_tree(target, depth=depth, show_hidden=_workspace_show_hidden, state=state)
    return {
        "path": path_value,
        "root": tree,
        "truncated": bool(state["truncated"]),
    }


async def _emit_workspace_updates(updates: list[dict]) -> None:
    global _workspace_last_emit_at
    if not updates or not _workspace_visible:
        return
    _workspace_last_emit_at = asyncio.get_running_loop().time()
    await broadcast_event("workspace_update", {"updates": updates})


async def _flush_workspace_updates_after(delay_s: float) -> None:
    global _workspace_throttle_task, _workspace_pending_updates
    try:
        await asyncio.sleep(delay_s)
    except asyncio.CancelledError:
        return
    updates = list(_workspace_pending_updates.values())
    _workspace_pending_updates = {}
    _workspace_throttle_task = None
    await _emit_workspace_updates(updates)


async def _schedule_workspace_updates(updates: list[dict]) -> None:
    global _workspace_throttle_task, _workspace_pending_updates
    if not updates:
        return
    loop = asyncio.get_running_loop()
    elapsed = loop.time() - _workspace_last_emit_at
    if elapsed >= _workspace_update_throttle_s and _workspace_throttle_task is None and not _workspace_pending_updates:
        await _emit_workspace_updates(updates)
        return
    for update in updates:
        _workspace_pending_updates[update["path"]] = update
    if _workspace_throttle_task is None:
        delay = max(_workspace_update_throttle_s - elapsed, 0.0)
        _workspace_throttle_task = asyncio.create_task(_flush_workspace_updates_after(delay))


async def _workspace_watch_loop(stop_event: Event) -> None:
    if awatch is None:
        await _workspace_poll_loop()
        return
    root = _workspace_root()
    try:
        async for changes in awatch(
            root,
            recursive=True,
            stop_event=stop_event,
            debounce=_workspace_watch_debounce_ms,
            step=_workspace_watch_step_ms,
        ):
            if not _workspace_visible:
                continue
            targets: set[str] = set()
            for _, changed in changes:
                changed_path = Path(changed).resolve()
                if not _is_within_workspace(changed_path):
                    continue
                rel = _to_workspace_relative(changed_path)
                rel_path = Path(rel)
                if _is_excluded_relative(rel_path):
                    continue
                if not _workspace_show_hidden and _is_hidden_relative(rel_path):
                    continue
                target = "." if rel == "." else _to_workspace_relative(changed_path.parent)
                targets.add(target)
            if not targets:
                continue
            updates = []
            for target in _compress_paths(list(targets)):
                update = _build_workspace_update(target)
                if update:
                    updates.append(update)
            await _schedule_workspace_updates(updates)
    except asyncio.CancelledError:
        raise


async def _set_workspace_visibility(visible: bool, show_hidden: bool) -> None:
    global _workspace_visible
    global _workspace_show_hidden
    global _workspace_poll_task
    global _workspace_watch_stop_event
    global _workspace_pending_updates
    global _workspace_throttle_task
    async with _workspace_poll_lock:
        _workspace_visible = visible
        _workspace_show_hidden = show_hidden
        if not visible:
            if _workspace_watch_stop_event is not None:
                _workspace_watch_stop_event.set()
            if _workspace_poll_task and not _workspace_poll_task.done():
                _workspace_poll_task.cancel()
                try:
                    await _workspace_poll_task
                except asyncio.CancelledError:
                    pass
            _workspace_poll_task = None
            _workspace_watch_stop_event = None
            _workspace_pending_updates = {}
            if _workspace_throttle_task and not _workspace_throttle_task.done():
                _workspace_throttle_task.cancel()
                try:
                    await _workspace_throttle_task
                except asyncio.CancelledError:
                    pass
            _workspace_throttle_task = None
            return

        await _broadcast_workspace_tree_if_changed(force=True)
        if _workspace_poll_task is None or _workspace_poll_task.done():
            if awatch is None:
                _workspace_poll_task = asyncio.create_task(_workspace_poll_loop())
            else:
                _workspace_watch_stop_event = Event()
                _workspace_poll_task = asyncio.create_task(_workspace_watch_loop(_workspace_watch_stop_event))


async def get_workspace_tree(request: web.Request) -> web.Response:
    path_value = request.query.get("path", "")
    depth = int(request.query.get("depth", DEFAULT_TREE_DEPTH))
    depth = max(0, min(MAX_TREE_DEPTH, depth))
    show_hidden = request.query.get("show_hidden", "0") in {"1", "true", "yes"}

    target = _resolve_workspace_path(path_value)
    if not target.exists():
        return web.json_response({"error": "Path not found"}, status=404)

    state: dict[str, int | bool] = {"count": 0, "truncated": False}
    tree = _build_tree(target, depth=depth, show_hidden=show_hidden, state=state)
    return web.json_response({"root": tree, "truncated": bool(state["truncated"])})


async def get_workspace_file(request: web.Request) -> web.Response:
    path_value = request.query.get("path")
    if not path_value:
        return web.json_response({"error": "Missing path"}, status=400)

    max_bytes = int(request.query.get("max", DEFAULT_PREVIEW_BYTES))
    max_bytes = max(256, min(MAX_PREVIEW_BYTES, max_bytes))

    target = _resolve_workspace_path(path_value)
    if not target.exists():
        return web.json_response({"error": "Path not found"}, status=404)
    if target.is_dir():
        return web.json_response({"error": "Path is a directory"}, status=400)

    rel_path = _to_workspace_relative(target)
    content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    stat = target.stat()
    base = {
        "path": rel_path,
        "size": stat.st_size,
        "mtime": _format_mtime(target),
        "content_type": content_type,
    }

    if content_type.startswith("image/"):
        return web.json_response({
            **base,
            "kind": "image",
            "url": f"/workspace/raw?path={rel_path}",
        })

    if _is_text_file(target, content_type):
        data = target.read_bytes()[: max_bytes + 1]
        truncated = len(data) > max_bytes
        if truncated:
            data = data[:max_bytes]
        text = data.decode("utf-8", errors="replace")
        return web.json_response({
            **base,
            "kind": "text",
            "text": text,
            "truncated": truncated,
        })

    return web.json_response({
        **base,
        "kind": "binary",
        "truncated": stat.st_size > max_bytes,
    })


async def update_workspace_file(request: web.Request) -> web.Response:
    """PUT /workspace/file – write content to a workspace file."""
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError):
        return web.json_response({"error": "Invalid JSON"}, status=400)

    path_value = data.get("path")
    if not path_value:
        return web.json_response({"error": "Missing path"}, status=400)

    content = data.get("content")
    if content is None:
        return web.json_response({"error": "Missing content"}, status=400)

    content_str = str(content)
    if len(content_str.encode("utf-8")) > MAX_FILE_WRITE_BYTES:
        return web.json_response({"error": "Content too large"}, status=413)

    target = _resolve_workspace_path(path_value)
    if target.is_dir():
        return web.json_response({"error": "Path is a directory"}, status=400)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content_str, encoding="utf-8")

    stat = target.stat()
    return web.json_response({
        "path": _to_workspace_relative(target),
        "size": stat.st_size,
        "mtime": _format_mtime(target),
    })


async def get_workspace_raw(request: web.Request) -> web.StreamResponse:
    path_value = request.query.get("path")
    if not path_value:
        return web.json_response({"error": "Missing path"}, status=400)
    target = _resolve_workspace_path(path_value)
    if not target.exists() or target.is_dir():
        return web.json_response({"error": "Path not found"}, status=404)
    return web.FileResponse(target)


async def attach_workspace_file(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    path_value = (data or {}).get("path")
    if not path_value:
        return web.json_response({"error": "Missing path"}, status=400)

    target = _resolve_workspace_path(path_value)
    if not target.exists() or target.is_dir():
        return web.json_response({"error": "Path not found"}, status=404)

    blob = target.read_bytes()
    content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    rel_path = _to_workspace_relative(target)

    db = await get_db()
    media_id = await db.create_media(
        filename=target.name,
        content_type=content_type,
        data=blob,
        thumbnail=None,
        metadata={
            "size": len(blob),
            "workspace_path": rel_path,
        },
    )
    return web.json_response({"media_id": media_id})


async def set_workspace_visibility_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    visible = bool((data or {}).get("visible", False))
    show_hidden = bool((data or {}).get("show_hidden", False))
    await _set_workspace_visibility(visible, show_hidden)
    return web.json_response({"ok": True, "visible": visible, "show_hidden": show_hidden})


async def shutdown_workspace_manager() -> None:
    await _set_workspace_visibility(False, _workspace_show_hidden)


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/workspace/tree", get_workspace_tree)
    app.router.add_get("/workspace/file", get_workspace_file)
    app.router.add_put("/workspace/file", update_workspace_file)
    app.router.add_get("/workspace/raw", get_workspace_raw)
    app.router.add_post("/workspace/attach", attach_workspace_file)
    app.router.add_post("/workspace/visibility", set_workspace_visibility_handler)
