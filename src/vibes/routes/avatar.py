"""Avatar serving routes for Vibes.

Serves locally-cached avatar images for agents and users via /avatar/{kind}.
"""

from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web

from ..avatar import ensure_avatar_cache
from ..config import get_config

logger = logging.getLogger(__name__)


async def get_avatar(request: web.Request) -> web.Response:
    """Serve a cached avatar image."""
    kind = request.match_info["kind"]
    if kind not in ("agent", "user"):
        return web.json_response({"error": "Invalid avatar kind"}, status=404)

    config = get_config()
    source = ""
    if kind == "agent":
        source = config.agent_avatar or ""
    elif kind == "user":
        source = config.user_avatar or ""

    if not source:
        return web.json_response({"error": "No avatar configured"}, status=404)

    meta = await ensure_avatar_cache(kind, source)
    if not meta:
        # Cache failed — redirect to the original URL as fallback
        raise web.HTTPFound(source)

    file_path = Path(meta["file"])
    if not file_path.exists():
        raise web.HTTPFound(source)

    data = file_path.read_bytes()
    return web.Response(
        body=data,
        content_type=meta.get("content_type", "application/octet-stream"),
        headers={
            "Cache-Control": "no-store",
        },
    )


def setup_routes(app: web.Application) -> None:
    """Set up avatar routes."""
    app.router.add_get("/avatar/{kind}", get_avatar)
