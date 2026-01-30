"""Media upload and serving route handlers."""

import io
from aiohttp import web
from PIL import Image
from ..db import get_db

MAX_THUMBNAIL_SIZE = 800
THUMBNAIL_QUALITY = 80
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


def generate_thumbnail(data: bytes, content_type: str) -> bytes | None:
    """Generate a thumbnail for an image."""
    if not content_type.startswith("image/"):
        return None
    
    try:
        img = Image.open(io.BytesIO(data))
        
        # Convert to RGB if necessary (for PNG with transparency, etc.)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # Resize if larger than max size
        if max(img.size) > MAX_THUMBNAIL_SIZE:
            img.thumbnail((MAX_THUMBNAIL_SIZE, MAX_THUMBNAIL_SIZE), Image.Resampling.LANCZOS)
        
        # Save as JPEG
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=THUMBNAIL_QUALITY)
        return output.getvalue()
    except Exception:
        return None


async def upload_media(request: web.Request) -> web.Response:
    """Handle media file upload."""
    reader = await request.multipart()
    
    field = await reader.next()
    if field is None or field.name != "file":
        return web.json_response({"error": "No file provided"}, status=400)
    
    filename = field.filename or "unnamed"
    content_type = field.headers.get("Content-Type", "application/octet-stream")
    
    # Read file data
    chunks = []
    size = 0
    while True:
        chunk = await field.read_chunk()
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_UPLOAD_SIZE:
            return web.json_response({"error": "File too large"}, status=413)
        chunks.append(chunk)
    
    data = b"".join(chunks)
    
    # Generate thumbnail for images
    thumbnail = generate_thumbnail(data, content_type)
    
    # Extract metadata
    metadata = {"size": len(data)}
    if content_type.startswith("image/"):
        try:
            img = Image.open(io.BytesIO(data))
            metadata["width"] = img.size[0]
            metadata["height"] = img.size[1]
        except Exception:
            pass
    
    db = await get_db()
    media_id = await db.create_media(
        filename=filename,
        content_type=content_type,
        data=data,
        thumbnail=thumbnail,
        metadata=metadata
    )
    
    return web.json_response({
        "id": media_id,
        "filename": filename,
        "content_type": content_type,
        "metadata": metadata
    }, status=201)


async def get_media(request: web.Request) -> web.Response:
    """Serve media file from database."""
    media_id = int(request.match_info["id"])
    
    db = await get_db()
    result = await db.get_media_data(media_id)
    
    if not result:
        return web.json_response({"error": "Media not found"}, status=404)
    
    content_type, data = result
    return web.Response(body=data, content_type=content_type)


async def get_media_thumbnail(request: web.Request) -> web.Response:
    """Serve media thumbnail from database."""
    media_id = int(request.match_info["id"])
    
    db = await get_db()
    result = await db.get_media_thumbnail(media_id)
    
    if not result:
        # Fall back to original if no thumbnail
        result = await db.get_media_data(media_id)
        if not result:
            return web.json_response({"error": "Media not found"}, status=404)
    
    content_type, data = result
    return web.Response(body=data, content_type=content_type)


async def get_media_info(request: web.Request) -> web.Response:
    """Get media metadata without data."""
    media_id = int(request.match_info["id"])
    
    db = await get_db()
    media = await db.get_media(media_id)
    
    if not media:
        return web.json_response({"error": "Media not found"}, status=404)
    
    return web.json_response(media)


def setup_routes(app: web.Application) -> None:
    """Set up media routes."""
    app.router.add_post("/media/upload", upload_media)
    app.router.add_get("/media/{id}", get_media)
    app.router.add_get("/media/{id}/thumbnail", get_media_thumbnail)
    app.router.add_get("/media/{id}/info", get_media_info)
