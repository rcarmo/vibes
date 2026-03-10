"""Main aiohttp application for Vibes."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from aiohttp import web

from .config import get_config
from .db import init_db, close_db, get_db, Database
from .middleware import create_auth_middleware, create_cors_middleware, create_security_middleware
from .tasks import start_task_queue, stop_task_queue
from .opengraph import reconcile_missing_previews
from .acp_client import start_agent as start_acp_agent, stop_agent as stop_acp_agent
from .pi_client import start_pi_agent, stop_pi_agent
from .routes import posts, media, sse, agents, workspace, avatar

logger = logging.getLogger(__name__)

# Propagate unbuffered behavior to child processes launched by the server.
os.environ.setdefault("PYTHONUNBUFFERED", "1")

# Path to static files (bundled with package)
STATIC_PATH = Path(__file__).parent / "static"


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.json_response({"status": "ok"})


async def manifest_handler(request: web.Request) -> web.Response:
    """Dynamic PWA manifest — uses agent name/avatar when configured."""
    config = get_config()
    name = config.agent_name or "Vibes"
    icons = [
        {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ]
    if config.agent_avatar:
        icons.insert(0, {"src": config.agent_avatar, "sizes": "192x192", "type": "image/png", "purpose": "any"})
    manifest = {
        "name": name,
        "short_name": name[:12] if len(name) > 12 else name,
        "description": "Slack-like interface for coding agents",
        "start_url": "/",
        "display": "standalone",
        "display_override": ["window-controls-overlay"],
        "background_color": "#000000",
        "theme_color": "#1d9bf0",
        "color_scheme": "dark light",
        "icons": icons,
    }
    return web.json_response(manifest)


async def index_handler(request: web.Request) -> web.FileResponse:
    """Serve the SPA index.html."""
    return web.FileResponse(STATIC_PATH / "index.html")


async def on_startup(app: web.Application) -> None:
    """Application startup handler."""
    config = get_config()
    await init_db(config.db_path)
    logger.info(f"Database initialized at {config.db_path}")
    
    await start_task_queue(num_workers=3)
    logger.info("Background task queue started")
    
    # Start the configured agent (only one at a time).
    if config.pi_enabled:
        if await start_pi_agent():
            logger.info(f"Pi agent started: {config.pi_agent}")
        else:
            logger.warning(f"Pi agent not available: {config.pi_agent}")
    else:
        if await start_acp_agent():
            logger.info(f"ACP agent started: {config.acp_agent}")
        else:
            logger.warning(f"ACP agent not available: {config.acp_agent}")
    
    # Reconcile missing link previews in background
    asyncio.create_task(reconcile_missing_previews())

    # Recover stale in-flight turns from a previous crash
    try:
        db_inst = await get_db()
        stale_count = await db_inst.clear_all_turns()
        if stale_count:
            logger.warning("Cleared %d stale in-flight turns from previous run", stale_count)
    except Exception:
        logger.warning("Failed to clear stale turns on startup", exc_info=True)


async def on_cleanup(app: web.Application) -> None:
    """Application cleanup handler."""
    logger.info("Shutting down...")
    
    if get_config().pi_enabled:
        await stop_pi_agent()
        logger.info("Pi agent stopped")
    else:
        await stop_acp_agent()
        logger.info("ACP agent stopped")
    
    await stop_task_queue()
    logger.info("Background task queue stopped")

    await workspace.shutdown_workspace_manager()
    logger.info("Workspace manager stopped")
    
    await close_db()
    logger.info("Database connection closed")


def create_app() -> web.Application:
    """Create and configure the aiohttp application."""
    app = web.Application(middlewares=[
        create_cors_middleware(),
        create_security_middleware(),
        create_auth_middleware(),
    ])
    
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
    avatar.setup_routes(app)
    workspace.setup_routes(app)
    
    # Dynamic PWA manifest (before static to take priority over static/manifest.json)
    app.router.add_get("/manifest.json", manifest_handler)
    
    # Static files and SPA fallback
    app.router.add_static("/static", STATIC_PATH, name="static")
    app.router.add_get("/", index_handler)
    
    return app


async def _run_whitelist(args: argparse.Namespace) -> int:
    db_path = args.db_path or get_config().db_path
    db = Database(db_path)
    await db.connect()
    try:
        if args.whitelist_command == "add":
            await db.add_to_whitelist(args.pattern, args.description)
            print(f"Added whitelist pattern: {args.pattern}")
            return 0
        if args.whitelist_command == "remove":
            removed = await db.remove_from_whitelist(args.pattern)
            if not removed:
                print(f"Pattern not found: {args.pattern}", file=sys.stderr)
                return 1
            print(f"Removed whitelist pattern: {args.pattern}")
            return 0
        if args.whitelist_command == "list":
            entries = await db.get_whitelist()
            if not entries:
                print("No whitelist entries.")
                return 0
            for entry in entries:
                description = entry.get("description") or ""
                if description:
                    print(f"{entry['pattern']}\t{description}")
                else:
                    print(entry["pattern"])
            return 0
        print("Unknown command", file=sys.stderr)
        return 2
    finally:
        await db.close()


def _run_server() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    config = get_config()
    app = create_app()
    
    logger.info(f"Starting Vibes on {config.host}:{config.port}")
    logger.info("Press Ctrl+C to stop")
    
    try:
        web.run_app(
            app, 
            host=config.host, 
            port=config.port,
            handle_signals=True,
            print=None  # Suppress default "Running on" message
        )
    except (KeyboardInterrupt, SystemExit):
        pass  # GracefulExit (from aiohttp signal handling) inherits SystemExit
    
    logger.info("Server stopped")


def main() -> None:
    """Entry point for the application."""
    parser = argparse.ArgumentParser(
        description="Vibes server and tools."
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Run the Vibes server.")

    whitelist_parser = subparsers.add_parser(
        "whitelist",
        help="Manage agent permission whitelist.",
    )
    whitelist_parser.add_argument(
        "--db-path",
        default=None,
        help="Override database path (default: VIBES_DB_PATH).",
    )
    whitelist_subparsers = whitelist_parser.add_subparsers(
        dest="whitelist_command",
        required=True,
    )
    whitelist_add = whitelist_subparsers.add_parser(
        "add",
        help="Add a whitelist pattern.",
    )
    whitelist_add.add_argument(
        "pattern",
        help="Whitelist pattern (supports '*').",
    )
    whitelist_add.add_argument(
        "--description",
        default=None,
        help="Optional description for the pattern.",
    )

    whitelist_remove = whitelist_subparsers.add_parser(
        "remove",
        help="Remove a whitelist pattern.",
    )
    whitelist_remove.add_argument(
        "pattern",
        help="Whitelist pattern to remove.",
    )

    whitelist_subparsers.add_parser(
        "list",
        help="List whitelist patterns.",
    )

    args = parser.parse_args()

    if args.command in (None, "serve"):
        _run_server()
        return
    if args.command == "whitelist":
        sys.exit(asyncio.run(_run_whitelist(args)))
    parser.print_help()


if __name__ == "__main__":
    main()
