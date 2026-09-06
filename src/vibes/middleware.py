"""HTTP middleware for the Vibes application.

Provides CORS handling, security headers, and an extensible auth gate
that can be wired up to TOTP/token/session auth in the future.

The auth middleware classifies each request path as public or protected
and calls a pluggable ``authenticate`` callback for protected routes.
The default callback is a no-op that allows all requests through.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit
from collections.abc import Awaitable, Callable

from aiohttp import web

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Route classification
# ---------------------------------------------------------------------------

# Paths that should never require authentication.
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/static/",
    "/avatar/",
)

# Exact paths that are public (login page, SSE negotiation, etc.)
PUBLIC_EXACT: frozenset[str] = frozenset({
    "/",
    "/health",
})


def is_public_route(path: str) -> bool:
    """Return True if *path* should be accessible without authentication."""
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


# ---------------------------------------------------------------------------
# Auth callback type
# ---------------------------------------------------------------------------

# The callback receives the request and returns ``None`` if authenticated
# or a ``web.Response`` (e.g. 401) to reject.
AuthCallback = Callable[[web.Request], Awaitable[web.Response | None]]


async def _allow_all(_request: web.Request) -> web.Response | None:
    """Default auth callback — allows every request (no auth configured)."""
    return None


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _apply_security_headers(response: web.StreamResponse) -> None:
    for key, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(key, value)


# ---------------------------------------------------------------------------
# Middleware factories
# ---------------------------------------------------------------------------

def create_cors_middleware() -> web.middleware:
    """CORS middleware with permissive policy (single-user app)."""

    @web.middleware
    async def cors_middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        origin = request.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or parsed.netloc != request.host:
                response = web.json_response({"error": "Cross-origin access denied"}, status=403)
                _apply_security_headers(response)
                return response
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)

        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, DELETE, OPTIONS"
        )
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization"
        )
        return response

    return cors_middleware


def create_security_middleware() -> web.middleware:
    """Append baseline security headers to every response."""

    @web.middleware
    async def security_middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        response = await handler(request)
        _apply_security_headers(response)
        return response

    return security_middleware


def create_auth_middleware(
    authenticate: AuthCallback = _allow_all,
) -> web.middleware:
    """Return middleware that gates protected routes behind *authenticate*.

    Public routes (health, static assets, avatars, login page) are always
    allowed through. Everything else is passed to the *authenticate*
    callback which may return a ``web.Response`` to reject the request.

    To enable authentication later, supply a callback that checks a
    session cookie, bearer token, or TOTP code and returns ``None`` on
    success or a 401/403 response on failure.  Example::

        async def check_token(request):
            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if not token or token != EXPECTED:
                return web.json_response({"error": "Unauthorized"}, status=401)
            return None

        create_auth_middleware(authenticate=check_token)
    """

    @web.middleware
    async def auth_middleware(
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        if not is_public_route(request.path):
            rejection = await authenticate(request)
            if rejection is not None:
                _apply_security_headers(rejection)
                return rejection

        return await handler(request)

    return auth_middleware
