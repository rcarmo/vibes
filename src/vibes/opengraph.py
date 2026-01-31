"""OpenGraph metadata fetching utility."""

import io
import re
import asyncio
import logging
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urlparse
from aiohttp import ClientSession, ClientTimeout
from PIL import Image

from .tasks import enqueue

logger = logging.getLogger(__name__)

# Simple pattern to find URL candidates - validation done by urlparse
URL_CANDIDATE_PATTERN = re.compile(r'https?://[^\s<>\[\]"\']+')

# Timeout for fetching URLs
FETCH_TIMEOUT = ClientTimeout(total=10)

# Image settings
MAX_PREVIEW_IMAGE_SIZE = 640  # Max width/height
PREVIEW_IMAGE_QUALITY = 85


class OpenGraphParser(HTMLParser):
    """HTML parser that extracts OpenGraph and meta tags."""
    
    def __init__(self):
        super().__init__()
        self.og_data = {}
        self.title = None
        self.description = None
        self.in_title = False
        self._title_content = []
    
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        if tag == 'title':
            self.in_title = True
            return
        
        if tag != 'meta':
            return
        
        # OpenGraph tags
        prop = attrs_dict.get('property', '')
        if prop.startswith('og:'):
            key = prop[3:]
            content = attrs_dict.get('content', '')
            if content:
                self.og_data[key] = content
        
        # Fallback meta tags
        name = attrs_dict.get('name', '').lower()
        content = attrs_dict.get('content', '')
        if name == 'description' and content and not self.description:
            self.description = content
    
    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
            if self._title_content:
                self.title = ''.join(self._title_content).strip()
    
    def handle_data(self, data):
        if self.in_title:
            self._title_content.append(data)
    
    def get_metadata(self) -> dict:
        """Return the extracted metadata with fallbacks."""
        return {
            'title': self.og_data.get('title') or self.title,
            'description': self.og_data.get('description') or self.description,
            'image': self.og_data.get('image'),
            'site_name': self.og_data.get('site_name'),
            'type': self.og_data.get('type'),
        }


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text content, excluding those in code blocks.
    
    Skips URLs inside:
    - Markdown code blocks (```...```)
    - Inline code (`...`)
    - HTML <pre> and <code> tags
    """
    import re
    
    # Remove code blocks from consideration
    # 1. Remove fenced code blocks (```...```)
    text_clean = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
    
    # 2. Remove inline code (`...`)
    text_clean = re.sub(r'`[^`]+`', '', text_clean)
    
    # 3. Remove <pre>...</pre> blocks
    text_clean = re.sub(r'<pre[^>]*>.*?</pre>', '', text_clean, flags=re.DOTALL | re.IGNORECASE)
    
    # 4. Remove <code>...</code> blocks
    text_clean = re.sub(r'<code[^>]*>.*?</code>', '', text_clean, flags=re.DOTALL | re.IGNORECASE)
    
    # Now extract URLs from the cleaned text
    candidates = URL_CANDIDATE_PATTERN.findall(text_clean)
    urls = []
    for candidate in candidates:
        # Strip trailing punctuation that's likely not part of the URL
        clean = candidate.rstrip('.,;:!?\'"')
        
        # Handle unbalanced trailing parentheses (markdown links)
        # Count parens - if more closing than opening, strip the excess
        while clean.endswith(')'):
            open_count = clean.count('(')
            close_count = clean.count(')')
            if close_count > open_count:
                clean = clean[:-1]
            else:
                break
        
        # Validate with urlparse
        parsed = urlparse(clean)
        if parsed.scheme and parsed.netloc:
            urls.append(clean)
    return urls


async def fetch_opengraph(url: str, session: Optional[ClientSession] = None) -> Optional[dict]:
    """Fetch OpenGraph metadata for a URL."""
    close_session = False
    if session is None:
        session = ClientSession(timeout=FETCH_TIMEOUT)
        close_session = True
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Vibes/1.0; +https://github.com/rcarmo/vibes)'
        }
        async with session.get(url, headers=headers, allow_redirects=True) as response:
            if response.status != 200:
                return None
            
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' not in content_type:
                return None
            
            # Read full response text (aiohttp handles encoding)
            html = await response.text(encoding='utf-8', errors='ignore')
            # Limit to first 100KB for parsing
            html = html[:102400]
            
            parser = OpenGraphParser()
            parser.feed(html)
            
            metadata = parser.get_metadata()
            metadata['url'] = str(response.url)  # Final URL after redirects
            
            # Only return if we got at least a title
            if metadata.get('title'):
                return metadata
            return None
    except Exception as e:
        logger.warning(f"Error fetching OpenGraph for {url}: {e}")
        return None
    finally:
        if close_session:
            await session.close()


async def download_and_cache_image(image_url: str, session: Optional[ClientSession] = None) -> Optional[int]:
    """Download an image, resize if needed, and cache in database. Returns media ID."""
    from .db import get_db
    
    # Check if we already have this image cached
    db = await get_db()
    existing_id = await db.get_media_by_original_url(image_url)
    if existing_id:
        logger.info(f"Using existing cached image for {image_url}: media/{existing_id}")
        return existing_id
    
    close_session = False
    if session is None:
        session = ClientSession(timeout=FETCH_TIMEOUT)
        close_session = True
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; Vibes/1.0; +https://github.com/rcarmo/vibes)'
        }
        async with session.get(image_url, headers=headers, allow_redirects=True) as response:
            if response.status != 200:
                logger.warning(f"Failed to download image {image_url}: HTTP {response.status}")
                return None
            
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                logger.warning(f"Not an image: {image_url} ({content_type})")
                return None
            
            # Read image data (limit to 5MB)
            data = await response.read()
            if len(data) > 5 * 1024 * 1024:
                logger.warning(f"Image too large: {image_url}")
                return None
            
            # Process image with PIL
            try:
                img = Image.open(io.BytesIO(data))
                
                # Convert to RGB if necessary
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                # Resize if too large
                if max(img.size) > MAX_PREVIEW_IMAGE_SIZE:
                    img.thumbnail((MAX_PREVIEW_IMAGE_SIZE, MAX_PREVIEW_IMAGE_SIZE), Image.Resampling.LANCZOS)
                    logger.info(f"Resized image from {image_url} to {img.size}")
                
                # Save as JPEG
                output = io.BytesIO()
                img.save(output, format="JPEG", quality=PREVIEW_IMAGE_QUALITY)
                processed_data = output.getvalue()
                
                metadata = {
                    "width": img.size[0],
                    "height": img.size[1],
                    "original_url": image_url,
                    "size": len(processed_data)
                }
            except Exception as e:
                logger.warning(f"Failed to process image {image_url}: {e}")
                return None
            
            # Extract filename from URL
            parsed = urlparse(image_url)
            filename = parsed.path.split('/')[-1] or 'preview.jpg'
            if not filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                filename = 'preview.jpg'
            
            # Store in database
            media_id = await db.create_media(
                filename=filename,
                content_type="image/jpeg",
                data=processed_data,
                thumbnail=processed_data,  # Use same image as thumbnail
                metadata=metadata
            )
            
            logger.info(f"Cached image from {image_url} as media/{media_id}")
            return media_id
            
    except Exception as e:
        logger.warning(f"Error downloading image {image_url}: {e}")
        return None
    finally:
        if close_session:
            await session.close()


async def fetch_link_previews(text: str, cache: Optional[dict[str, dict]] = None) -> list[dict]:
    """Extract URLs from text and fetch OpenGraph metadata for each.
    
    Args:
        text: Text content that may contain URLs
        cache: Optional URL -> preview cache to reuse existing previews
    """
    urls = extract_urls(text)
    if not urls:
        return []
    
    # Limit to first 4 URLs
    urls = urls[:4]
    
    previews = []
    urls_to_fetch = []
    
    # Check cache first
    if cache:
        for url in urls:
            if url in cache:
                logger.info(f"Using cached preview for {url}")
                previews.append(cache[url])
            else:
                urls_to_fetch.append(url)
    else:
        urls_to_fetch = urls
    
    # Fetch uncached URLs
    if urls_to_fetch:
        async with ClientSession(timeout=FETCH_TIMEOUT) as session:
            tasks = [fetch_opengraph(url, session) for url in urls_to_fetch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and download images
            for result in results:
                if isinstance(result, dict) and result:
                    # Download and cache the image if present
                    if result.get('image'):
                        media_id = await download_and_cache_image(result['image'], session)
                        if media_id:
                            # Replace remote URL with local media URL
                            result['image'] = f'/media/{media_id}'
                            result['image_media_id'] = media_id
                        else:
                            # Failed to cache, remove image to avoid hotlink issues
                            result['image'] = None
                    previews.append(result)
    
    return previews


async def fetch_and_update_previews(interaction_id: int, content: str, use_cache: bool = True):
    """Background task to fetch link previews and update the interaction."""
    from .db import get_db
    from .routes.sse import broadcast_event
    
    urls = extract_urls(content)
    if not urls:
        return
    
    logger.info(f"Fetching link previews for interaction {interaction_id}, URLs: {urls}")
    
    try:
        # Get cache if requested
        cache = None
        db = await get_db()
        if use_cache:
            cache = await db.get_all_cached_previews()
            logger.info(f"Loaded {len(cache)} cached previews")
        
        previews = await fetch_link_previews(content, cache)
        if not previews:
            logger.info(f"No previews found for interaction {interaction_id}")
            return
        
        # Update interaction in database
        await db.update_interaction_previews(interaction_id, previews)
        
        # Fetch updated interaction and broadcast
        interaction = await db.get_interaction(interaction_id)
        if interaction:
            await broadcast_event("interaction_updated", interaction)
            logger.info(f"Broadcast update for interaction {interaction_id} with {len(previews)} previews")
    except Exception as e:
        logger.error(f"Error fetching previews for interaction {interaction_id}: {e}", exc_info=True)


def queue_link_preview_fetch(interaction_id: int, content: str):
    """Queue a background task to fetch link previews."""
    urls = extract_urls(content)
    if not urls:
        return
    logger.info(f"Queueing link preview fetch for interaction {interaction_id}")
    enqueue(fetch_and_update_previews, interaction_id, content)


async def reconcile_missing_previews():
    """Scan database for posts missing previews and queue fetches."""
    from .db import get_db
    
    logger.info("Reconciling missing link previews...")
    
    db = await get_db()
    interactions = await db.get_interactions_missing_previews()
    
    # Filter to only those with actual URLs
    to_fetch = []
    for interaction in interactions:
        content = interaction["data"].get("content", "")
        if extract_urls(content):
            to_fetch.append(interaction)
    
    if not to_fetch:
        logger.info("No interactions missing previews")
        return
    
    logger.info(f"Found {len(to_fetch)} interactions missing previews, queueing...")
    
    for interaction in to_fetch:
        content = interaction["data"].get("content", "")
        enqueue(fetch_and_update_previews, interaction["id"], content, True)
