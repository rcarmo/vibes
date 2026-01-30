"""Main aiohttp application for Vibes."""

import asyncio
import logging
from pathlib import Path
from aiohttp import web

from .config import get_config
from .db import init_db, close_db
from .routes import posts, media, sse, agents

logger = logging.getLogger(__name__)

# Path to static files (bundled with package)
STATIC_PATH = Path(__file__).parent / "static"


def create_cors_middleware():
    """Create CORS middleware with open policy."""
    @web.middleware
    async def cors_middleware(request: web.Request, handler):
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)
        
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
    
    return cors_middleware


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({"status": "ok"})


async def index_handler(request: web.Request) -> web.FileResponse:
    """Serve the SPA index.html."""
    return web.FileResponse(STATIC_PATH / "index.html")


async def on_startup(app: web.Application) -> None:
    """Application startup handler."""
    config = get_config()
    await init_db(config.db_path)
    logger.info(f"Database initialized at {config.db_path}")


async def on_cleanup(app: web.Application) -> None:
    """Application cleanup handler."""
    await close_db()
    logger.info("Database connection closed")


def create_app() -> web.Application:
    """Create and configure the aiohttp application."""
    app = web.Application(middlewares=[create_cors_middleware()])
    
    # Lifecycle handlers
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    # Health check
    app.router.add_get("/health", health_check)
    
    # API routes
    posts.setup_routes(app)
    media.setup_routes(app)
    sse.setup_routes(app)
    agents.setup_routes(app)
    
    # Static files and SPA fallback
    app.router.add_static("/static", STATIC_PATH, name="static")
    app.router.add_get("/", index_handler)
    
    return app


def main() -> None:
    """Entry point for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    config = get_config()
    app = create_app()
    
    logger.info(f"Starting Vibes on {config.host}:{config.port}")
    web.run_app(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
