"""Serve the pinned Classic bundle without shadowing backend routes."""

from pathlib import Path

from aiohttp import web

ASSET_DIRECTORIES = ('dist', 'css', 'fonts', 'js', 'editor-vendor', 'common')
ASSET_FILES = ('favicon.ico', 'icon-192.png', 'icon-512.png', 'robots.txt')
VIEWERS = ('html-viewer', 'image-viewer', 'video-viewer', 'pdf-viewer', 'data-viewer')
_RESERVED = frozenset(('api', 'agent', 'auth', 'sse', 'workspace', 'terminal', 'vnc',
                       'media', 'post', 'posts', 'sessions', 'health', 'diagnostics',
                       'avatar', 'static', *ASSET_DIRECTORIES, *VIEWERS))


def is_asset_path(path: str) -> bool:
    """Only public bundle paths, never runtime APIs or workspace contents."""
    return path.startswith(('/static/', *(f'/{name}/' for name in ASSET_DIRECTORIES))) or path in {
        f'/{name}' for name in ASSET_FILES
    }


def _viewer_policy(name: str) -> str:
    # Pinned Piclaw viewers-3.3.4/csp.json. Keep the iframe exception page-specific.
    policy = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    policy += "img-src 'self' data: blob:" + (' https: http:' if name == 'html-viewer' else '') + '; '
    if name == 'video-viewer':
        policy += "media-src 'self' data: blob:; "
    policy += "connect-src 'self'; frame-src 'self'" + ('' if name == 'data-viewer' else ' blob:')
    return policy + "; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"


def setup_asset_routes(app: web.Application, root: Path, index_handler) -> None:
    """Register explicit assets after APIs; leave unknown API paths as 404."""
    for directory in ASSET_DIRECTORIES:
        if (root / directory).is_dir():
            app.router.add_static(f'/{directory}', root / directory)

    def file_handler(path: Path, headers=None):
        async def serve(_request):
            return web.FileResponse(path, headers=headers)
        return serve

    for name in ASSET_FILES:
        if (root / name).is_file():
            app.router.add_get(f'/{name}', file_handler(root / name))
    for name in VIEWERS:
        if (root / name).is_dir():
            headers = {'Content-Security-Policy': _viewer_policy(name),
                       'X-Frame-Options': 'SAMEORIGIN', 'Cache-Control': 'no-cache'}
            app.router.add_get(f'/{name}/', file_handler(root / name / 'index.html', headers))
            app.router.add_static(f'/{name}', root / name)

    async def spa_fallback(request):
        parts = request.path.strip('/').split('/')
        if parts[0] in _RESERVED or any('.' in part for part in parts):
            raise web.HTTPNotFound()
        return await index_handler(request)

    app.router.add_get('/{app_route:.*}', spa_fallback)
