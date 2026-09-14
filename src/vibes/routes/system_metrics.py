"""Authenticated host metrics endpoint using the app's normal middleware."""
from aiohttp import web
from ..system_metrics import SystemMetrics

METRICS_KEY = web.AppKey('system_metrics', SystemMetrics)


async def get_metrics(request):
    return web.json_response(await request.app[METRICS_KEY].get(), headers={'Cache-Control': 'no-store'})


def setup_routes(app):
    app[METRICS_KEY] = SystemMetrics()
    app.router.add_get('/system/metrics', get_metrics)
