import importlib
import pytest

media_response = importlib.import_module('vibes.routes.media').media_response


@pytest.mark.parametrize('mime', ['text/html', 'image/svg+xml', 'application/pdf', 'application/octet-stream'])
def test_active_or_generic_media_downloads(mime):
    response = media_response(b'<script>alert(1)</script>', mime)
    assert response.headers['Content-Disposition'] == 'attachment'
    assert response.headers['Content-Security-Policy'].startswith('sandbox')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'


def test_raster_remains_inline():
    response = media_response(b'png', 'image/png')
    assert 'Content-Disposition' not in response.headers
