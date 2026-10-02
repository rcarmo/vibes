"""FFI preview network boundary, distinct from user authentication."""

from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host,peer,status",
    [
        ("127.0.0.1:1234", "127.0.0.1", 200),
        ("localhost:1234", "::1", 200),
        ("[::1]:1234", "::1", 200),
        ("evil.example:1234", "127.0.0.1", 403),
        ("127.0.0.1:1234", "192.0.2.1", 403),
        ("evil.example", "192.0.2.1", 403),
    ],
)
async def test_loopback_rejects_rebinding_and_remote_peers(host, peer, status):
    from vibes.middleware import create_loopback_middleware

    request = make_mocked_request("GET", "/health", headers={"Host": host})
    request._cache["remote"] = peer
    handler = AsyncMock(return_value=web.Response(text="ok"))
    response = await create_loopback_middleware()(request, handler)
    assert response.status == status
    if status != 200:
        handler.assert_not_awaited()


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "example.com", "192.0.2.1"])
def test_config_refuses_ffi_network_bind(monkeypatch, host):
    from vibes import config

    monkeypatch.setattr(config, "_load_settings_file", lambda: {})
    monkeypatch.setenv("VIBES_DEFAULT_AGENT", "copilot-ffi")
    monkeypatch.setenv("VIBES_HOST", host)
    with pytest.raises(ValueError, match="loopback"):
        config.Config()
