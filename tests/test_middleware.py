"""Tests for vibes.middleware."""

import importlib
import sys
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) in sys.path:
    sys.path.remove(str(SRC_PATH))
sys.path.insert(0, str(SRC_PATH))

for module_name in list(sys.modules.keys()):
    if module_name == "vibes" or module_name.startswith("vibes."):
        sys.modules.pop(module_name, None)

mw = importlib.import_module("vibes.middleware")


class TestRouteClassification:
    def test_health_is_public(self):
        assert mw.is_public_route("/health") is True

    def test_root_is_public(self):
        assert mw.is_public_route("/") is True

    def test_static_is_public(self):
        assert mw.is_public_route("/static/js/app.js") is True

    def test_avatar_is_public(self):
        assert mw.is_public_route("/avatar/agent") is True

    def test_api_is_protected(self):
        assert mw.is_public_route("/agents") is False
        assert mw.is_public_route("/timeline") is False
        assert mw.is_public_route("/workspace/tree") is False
        assert mw.is_public_route("/sse/stream") is False


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_public_route_bypasses_auth(self):
        """Public routes should never invoke the auth callback."""
        called = False

        async def reject_all(_req):
            nonlocal called
            called = True
            return web.json_response({"error": "Unauthorized"}, status=401)

        middleware = mw.create_auth_middleware(authenticate=reject_all)

        async def handler(_req):
            return web.Response(text="ok")

        request = make_mocked_request("GET", "/health")
        resp = await middleware(request, handler)
        assert resp.status == 200
        assert called is False

    @pytest.mark.asyncio
    async def test_protected_route_calls_auth(self):
        """Protected routes should call the auth callback."""
        async def reject_all(_req):
            return web.json_response({"error": "Unauthorized"}, status=401)

        middleware = mw.create_auth_middleware(authenticate=reject_all)

        async def handler(_req):
            return web.Response(text="ok")

        request = make_mocked_request("GET", "/agents")
        resp = await middleware(request, handler)
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_default_auth_allows_all(self):
        """Default auth (no callback) allows everything through."""
        middleware = mw.create_auth_middleware()

        async def handler(_req):
            return web.Response(text="ok")

        request = make_mocked_request("GET", "/agents")
        resp = await middleware(request, handler)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_auth_success_passes_through(self):
        """When auth callback returns None, the request proceeds."""
        async def allow_all(_req):
            return None

        middleware = mw.create_auth_middleware(authenticate=allow_all)

        async def handler(_req):
            return web.Response(text="ok")

        request = make_mocked_request("GET", "/timeline")
        resp = await middleware(request, handler)
        assert resp.status == 200


class TestSecurityMiddleware:
    @pytest.mark.asyncio
    async def test_adds_security_headers(self):
        middleware = mw.create_security_middleware()

        async def handler(_req):
            return web.Response(text="ok")

        request = make_mocked_request("GET", "/agents")
        resp = await middleware(request, handler)
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert "Referrer-Policy" in resp.headers


class TestCorsMiddleware:
    @pytest.mark.asyncio
    async def test_options_returns_cors_headers(self):
        middleware = mw.create_cors_middleware()

        async def handler(_req):
            return web.Response(text="ok")

        request = make_mocked_request("OPTIONS", "/agents")
        resp = await middleware(request, handler)
        assert resp.headers["Access-Control-Allow-Origin"] == "*"
        assert "DELETE" in resp.headers["Access-Control-Allow-Methods"]

    @pytest.mark.asyncio
    async def test_normal_request_gets_cors_headers(self):
        middleware = mw.create_cors_middleware()

        async def handler(_req):
            return web.Response(text="ok")

        request = make_mocked_request("GET", "/agents")
        resp = await middleware(request, handler)
        assert resp.status == 200
        assert resp.headers["Access-Control-Allow-Origin"] == "*"

@pytest.mark.asyncio
async def test_cross_origin_workspace_access_denied():
    middleware = mw.create_cors_middleware()
    called = False

    async def handler(_req):
        nonlocal called
        called = True
        return web.Response(text="private")

    request = make_mocked_request("GET", "/workspace/file", headers={"Host": "localhost:8765", "Origin": "https://evil.example"})
    response = await middleware(request, handler)
    assert response.status == 403
    assert not called


def test_health_prefix_does_not_bypass_auth():
    assert not mw.is_public_route("/health-private")
