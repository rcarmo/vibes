import { html, render, useState, useEffect, useCallback, useRef } from './vendor/preact-htm.js';
import { getTimeline, getPostsByHashtag, searchPosts, getThread, createPost, sendAgentMessage, uploadMedia, getThumbnailUrl, getMediaUrl, getMediaInfo, respondToAgentRequest, addToWhitelist, getAgents, SSEClient } from './api.js';

// URL regex for linkifying text
const URL_REGEX = /(https?:\/\/[^\s<>"{}|\\^`\[\]]+)/g;
// Hashtag regex
const HASHTAG_REGEX = /#(\w+)/g;

// Configure marked for safe rendering
if (window.marked) {
    marked.setOptions({
        breaks: true,  // Convert \n to <br>
        gfm: true,     // GitHub Flavored Markdown
    });
}

/**
 * Decode HTML entities
 */
function decodeEntities(text) {
    if (!text) return text;
    // Use a more robust decoding that handles all entity types
    const doc = new DOMParser().parseFromString(text, 'text/html');
    return doc.documentElement.textContent;
}

/**
 * Render LaTeX math expressions using KaTeX
 * Handles $$...$$ for display math and $...$ for inline math
 */
function renderMath(html_content) {
    if (!window.katex) return html_content;
    
    // Process display math first ($$...$$) - must not be inside code blocks
    html_content = html_content.replace(/\$\$([\s\S]+?)\$\$/g, (match, tex) => {
        try {
            return katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false });
        } catch (e) {
            return `<span class="math-error" title="${e.message}">${match}</span>`;
        }
    });
    
    // Process inline math ($...$) - avoid matching $$ or currency like $100
    html_content = html_content.replace(/(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)/g, (match, tex) => {
        // Skip if it looks like currency ($ followed by number)
        if (/^\d/.test(tex.trim())) return match;
        try {
            return katex.renderToString(tex.trim(), { displayMode: false, throwOnError: false });
        } catch (e) {
            return `<span class="math-error" title="${e.message}">${match}</span>`;
        }
    });
    
    return html_content;
}

/**
 * Render markdown and then linkify hashtags
 */
function renderMarkdown(text, onHashtagClick) {
    if (!text) return '';
    
    // Decode HTML entities first (in case content has encoded entities)
    const decoded = decodeEntities(text);
    
    // Render markdown to HTML
    let html_content = window.marked ? marked.parse(decoded) : decoded.replace(/\n/g, '<br>');
    
    // Decode any entities that marked might have introduced
    html_content = html_content.replace(/&#(\d+);/g, (match, num) => String.fromCharCode(num));
    html_content = html_content.replace(/&#x([0-9a-fA-F]+);/g, (match, hex) => String.fromCharCode(parseInt(hex, 16)));
    
    // Render math expressions
    html_content = renderMath(html_content);
    
    // Process hashtags - wrap them in clickable spans (will be handled by event delegation)
    html_content = html_content.replace(HASHTAG_REGEX, '<a href="#" class="hashtag" data-hashtag="$1">#$1</a>');
    
    // Mark mermaid code blocks for async rendering
    // They appear as <pre><code class="language-mermaid">...</code></pre>
    html_content = html_content.replace(
        /<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g,
        (match, code) => {
            const decoded = decodeEntities(code.trim());
            const encoded = btoa(unescape(encodeURIComponent(decoded)));
            return `<div class="mermaid-container" data-mermaid="${encoded}"><div class="mermaid-loading">Loading diagram...</div></div>`;
        }
    );
    
    return html_content;
}

/**
 * Render markdown for thinking panels (no hashtag linkifying).
 */
function renderThinkingMarkdown(text) {
    if (!text) return '';
    const decoded = decodeEntities(text);
    let html_content = window.marked ? marked.parse(decoded) : decoded.replace(/\n/g, '<br>');
    html_content = html_content.replace(/&#(\d+);/g, (match, num) => String.fromCharCode(num));
    html_content = html_content.replace(/&#x([0-9a-fA-F]+);/g, (match, hex) => String.fromCharCode(parseInt(hex, 16)));
    html_content = renderMath(html_content);
    return html_content;
}

// Render pending mermaid diagrams in the DOM
async function renderMermaidDiagrams(container) {
    if (!window.beautifulMermaid) return;
    
    const { renderMermaid, THEMES } = window.beautifulMermaid;
    const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = isDark ? THEMES['tokyo-night'] : THEMES['github-light'];
    
    const pending = container.querySelectorAll('.mermaid-container[data-mermaid]');
    for (const el of pending) {
        try {
            const encoded = el.dataset.mermaid;
            const code = decodeURIComponent(escape(atob(encoded)));
            const svg = await renderMermaid(code, { ...theme, transparent: true });
            el.innerHTML = svg;
            el.removeAttribute('data-mermaid');
        } catch (e) {
            console.error('Mermaid render error:', e);
            el.innerHTML = `<pre class="mermaid-error">Diagram error: ${e.message}</pre>`;
            el.removeAttribute('data-mermaid');
        }
    }
}

/**
 * Linkify text - convert URLs and hashtags to clickable elements (for non-markdown contexts)
 */
function linkifyContent(text, onHashtagClick) {
    if (!text) return text;
    
    // First split by URLs
    const urlParts = text.split(URL_REGEX);
    
    return urlParts.map((part, i) => {
        // Check if this part is a URL
        if (URL_REGEX.test(part)) {
            URL_REGEX.lastIndex = 0;
            return html`<a href=${part} target="_blank" rel="noopener noreferrer" onClick=${(e) => e.stopPropagation()} class="content-link">${part}</a>`;
        }
        
        // Process hashtags in non-URL parts
        const hashtagParts = part.split(HASHTAG_REGEX);
        if (hashtagParts.length === 1) return part;
        
        return hashtagParts.map((hpart, j) => {
            // Every odd index is a captured hashtag (without #)
            if (j % 2 === 1) {
                return html`<a href="#" class="hashtag" onClick=${(e) => { e.preventDefault(); e.stopPropagation(); onHashtagClick?.(hpart); }}>#${hpart}</a>`;
            }
            return hpart;
        });
    });
}

/**
 * Format relative time
 */
function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = (now - date) / 1000;
    
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d`;
    return date.toLocaleDateString();
}

/**
 * Detect iOS devices for layout adjustments.
 */
function isIOSDevice() {
    if (/iPad|iPhone/.test(navigator.userAgent)) {
        return true;
    }
    // iPadOS Safari (desktop mode) reports as MacIntel with touch points.
    return navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
}

/**
 * Hook to force re-render for updating timestamps
 */
function useTimestampRefresh(intervalMs = 30000) {
    const [, setTick] = useState(0);
    
    useEffect(() => {
        const timer = setInterval(() => setTick(t => t + 1), intervalMs);
        return () => clearInterval(timer);
    }, [intervalMs]);
}

/**
 * Get avatar letter and color from name
 * Returns object with { letter, color }
 */
function getAvatarInfo(name) {
    if (!name) name = 'Agent';
    const letter = name.charAt(0).toUpperCase();
    
    // Generate a consistent color based on the letter
    const colors = [
        '#FF6B6B', // red
        '#4ECDC4', // teal
        '#45B7D1', // blue
        '#FFA07A', // light salmon
        '#98D8C8', // mint
        '#F7DC6F', // yellow
        '#BB8FCE', // purple
        '#85C1E2', // sky blue
        '#F8B195', // peach
        '#6C5CE7', // indigo
        '#00B894', // green
        '#FDCB6E', // gold
        '#E17055', // terracotta
        '#74B9FF', // light blue
        '#A29BFE', // lavender
        '#FD79A8', // pink
        '#00CEC9', // cyan
        '#FFEAA7', // light yellow
        '#DFE6E9', // light grey
        '#FF7675', // coral
        '#55EFC4', // aqua
        '#81ECEC', // light cyan
        '#FAB1A0', // salmon
        '#74B9FF', // periwinkle
        '#A29BFE', // soft purple
        '#FD79A8'  // rose
    ];
    
    // Use char code to pick a color consistently
    const index = letter.charCodeAt(0) % colors.length;
    const color = colors[index];
    
    return { letter, color };
}

function getAgentName(agentId, agents) {
    if (!agentId) return 'Agent';
    const name = agents[agentId]?.name || agentId;
    return name ? name.charAt(0).toUpperCase() + name.slice(1) : 'Agent';
}

/**
 * Update browser theme color (affects mobile chrome and PWA title bar)
 */
function updateThemeColor(dark) {
    const color = dark ? '#000000' : '#ffffff';
    let meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
        meta.setAttribute('content', color);
    }
}

/**
 * Compose box component
 */
function ComposeBox({ onPost, onFocus, searchMode, onSearch, onEnterSearch, onExitSearch }) {
    const [content, setContent] = useState('');
    const [searchText, setSearchText] = useState('');
    const [loading, setLoading] = useState(false);
    const [mediaFiles, setMediaFiles] = useState([]);
    const textareaRef = useRef(null);
    
    const handleSubmit = async () => {
        if (!content.trim() && mediaFiles.length === 0) return;
        
        setLoading(true);
        try {
            // Upload media files first
            const mediaIds = [];
            for (const file of mediaFiles) {
                const result = await uploadMedia(file);
                mediaIds.push(result.id);
            }
            
            // Send to agent by default
            await sendAgentMessage('default', content, null, mediaIds);
            
            setContent('');
            setMediaFiles([]);
            onPost?.();
        } catch (error) {
            console.error('Failed to post:', error);
            alert('Failed to post: ' + error.message);
        } finally {
            setLoading(false);
        }
    };
    
    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (searchMode) {
                if (searchText.trim()) {
                    onSearch?.(searchText.trim());
                }
            } else {
                handleSubmit();
            }
        }
    };
    
    const handleFileChange = (e) => {
        setMediaFiles([...e.target.files]);
    };
    
    // Auto-resize textarea
    const handleInput = (e) => {
        const value = e.target.value;
        if (searchMode) {
            setSearchText(value);
        } else {
            setContent(value);
        }
        const textarea = textareaRef.current;
        if (textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
        }
    };
    
    return html`
        <div class="compose-box">
            <div class="compose-input-wrapper">
                <textarea
                    ref=${textareaRef}
                    placeholder=${searchMode ? "Search (Enter to run)..." : "Message (Enter to send, Shift+Enter for newline)..."}
                    value=${searchMode ? searchText : content}
                    onInput=${handleInput}
                    onKeyDown=${handleKeyDown}
                    onFocus=${onFocus}
                    onClick=${onFocus}
                    disabled=${loading}
                    rows="1"
                />
                <div class="compose-actions ${searchMode ? 'search-mode' : ''}">
                    <button
                        class="icon-btn search-toggle"
                        onClick=${searchMode ? onExitSearch : onEnterSearch}
                        title=${searchMode ? "Close search" : "Search"}
                    >
                        ${searchMode ? html`
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M18 6L6 18M6 6l12 12"/>
                            </svg>
                        ` : html`
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="11" cy="11" r="8"/>
                                <path d="M21 21l-4.35-4.35"/>
                            </svg>
                        `}
                    </button>
                    ${!searchMode && html`
                        <label class="icon-btn" title="Attach image">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                            <input type="file" accept="image/*" multiple hidden onChange=${handleFileChange} />
                        </label>
                        <button 
                            class="icon-btn send-btn" 
                            onClick=${handleSubmit}
                            disabled=${loading || (!content.trim() && mediaFiles.length === 0)}
                            title="Send (Ctrl+Enter)"
                        >
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                        </button>
                    `}
                </div>
            </div>
            ${mediaFiles.length > 0 && html`
                <div class="media-files-preview">
                    ${mediaFiles.map(f => html`<span key=${f.name} class="media-file-tag">${f.name}</span>`)}
                </div>
            `}
        </div>
    `;
}

/**
 * Image modal for zooming
 */
function ImageModal({ src, onClose }) {
    useEffect(() => {
        const handleEsc = (e) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('keydown', handleEsc);
        return () => document.removeEventListener('keydown', handleEsc);
    }, [onClose]);
    
    return html`
        <div class="image-modal" onClick=${onClose}>
            <img src=${src} alt="Full size" />
        </div>
    `;
}

/**
 * File attachment component - displays downloadable file with icon
 */
function FileAttachment({ mediaId }) {
    const [info, setInfo] = useState(null);
    
    useEffect(() => {
        getMediaInfo(mediaId).then(setInfo).catch(() => {});
    }, [mediaId]);
    
    if (!info) return null;
    
    const filename = info.filename || 'file';
    const size = info.metadata?.size;
    const sizeStr = size ? formatFileSize(size) : '';
    
    return html`
        <a href=${getMediaUrl(mediaId)} download=${filename} class="file-attachment" onClick=${(e) => e.stopPropagation()}>
            <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
                <polyline points="10 9 9 9 8 9"/>
            </svg>
            <div class="file-info">
                <span class="file-name">${filename}</span>
                ${sizeStr && html`<span class="file-size">${sizeStr}</span>`}
            </div>
            <svg class="download-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
        </a>
    `;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatTimestamp(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
}

/**
 * Render annotations (audience/priority/lastModified)
 */
function AnnotationsBadge({ annotations }) {
    if (!annotations) return null;
    const { audience, priority, lastModified } = annotations;
    const formattedLastModified = lastModified ? formatTimestamp(lastModified) : null;
    return html`
        <div class="content-annotations">
            ${audience && audience.length > 0 && html`
                <span class="content-annotation">Audience: ${audience.join(', ')}</span>
            `}
            ${typeof priority === 'number' && html`
                <span class="content-annotation">Priority: ${priority}</span>
            `}
            ${formattedLastModified && html`
                <span class="content-annotation">Updated: ${formattedLastModified}</span>
            `}
        </div>
    `;
}

/**
 * Resource link block (MCP/ACP)
 */
function ResourceLinkBlock({ block }) {
    const name = block.title || block.name || block.uri;
    const description = block.description;
    const sizeStr = block.size ? formatFileSize(block.size) : '';
    const mimeType = block.mime_type || '';
    const icon = getMimeIcon(mimeType);
    return html`
        <a href=${block.uri} class="resource-link" target="_blank" rel="noopener noreferrer" onClick=${(e) => e.stopPropagation()}>
            <div class="resource-link-main">
                <div class="resource-link-header">
                    <span class="resource-link-icon-inline">${icon}</span>
                    <div class="resource-link-title">${name}</div>
                </div>
                ${description && html`<div class="resource-link-description">${description}</div>`}
                <div class="resource-link-meta">
                    ${mimeType && html`<span>${mimeType}</span>`}
                    ${sizeStr && html`<span>${sizeStr}</span>`}
                </div>
            </div>
            <div class="resource-link-icon">↗</div>
        </a>
    `;
}

/**
 * Embedded resource block (MCP/ACP)
 */
function ResourceBlock({ block }) {
    const [open, setOpen] = useState(false);
    const title = block.uri || 'Embedded resource';
    const contentText = block.text || '';
    const hasBlob = Boolean(block.data);
    const mimeType = block.mime_type || '';
    return html`
        <div class="resource-embed">
            <button class="resource-embed-toggle" onClick=${(e) => { e.preventDefault(); e.stopPropagation(); setOpen(!open); }}>
                ${open ? '▼' : '▶'} ${title}
            </button>
            ${open && html`
                ${contentText && html`<pre class="resource-embed-content">${contentText}</pre>`}
                ${hasBlob && html`
                    <div class="resource-embed-blob">
                        <span class="resource-embed-blob-label">Embedded blob</span>
                        ${mimeType && html`<span class="resource-embed-blob-meta">${mimeType}</span>`}
                        <button class="resource-embed-blob-btn" onClick=${(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            const blob = new Blob([Uint8Array.from(atob(block.data), c => c.charCodeAt(0))], { type: mimeType || 'application/octet-stream' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = title.split('/').pop() || 'resource';
                            a.click();
                            URL.revokeObjectURL(url);
                        }}>Download</button>
                    </div>
                `}
            `}
        </div>
    `;
}

function getMimeIcon(mimeType) {
    if (!mimeType) return '📎';
    if (mimeType.startsWith('image/')) return '🖼️';
    if (mimeType.startsWith('audio/')) return '🎵';
    if (mimeType.startsWith('video/')) return '🎬';
    if (mimeType.includes('pdf')) return '📄';
    if (mimeType.includes('zip') || mimeType.includes('gzip')) return '🗜️';
    if (mimeType.startsWith('text/')) return '📄';
    return '📎';
}

/**
 * Link preview component - card with image background
 */
function LinkPreview({ preview }) {
    const bgStyle = preview.image 
        ? `background-image: url('${preview.image}')`
        : '';
    
    return html`
        <a href=${preview.url} class="link-preview ${preview.image ? 'has-image' : ''}" target="_blank" rel="noopener noreferrer" onClick=${(e) => e.stopPropagation()} style=${bgStyle}>
            <div class="link-preview-overlay">
                <div class="link-preview-site">${preview.site_name || new URL(preview.url).hostname}</div>
                <div class="link-preview-title">${preview.title}</div>
                ${preview.description && html`
                    <div class="link-preview-description">${preview.description}</div>
                `}
            </div>
        </a>
    `;
}

/**
 * Remove URLs from text that have previews, but only if at the end
 */
function removePreviewedUrls(text, linkPreviews) {
    if (!linkPreviews?.length) return text;
    
    let result = text;
    for (const preview of linkPreviews) {
        const escapedUrl = preview.url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        // Only remove URL if it's at the end of the text (with optional trailing whitespace)
        result = result.replace(new RegExp(escapedUrl + '\\s*$', ''), '');
    }
    return result.trim();
}

/**
 * Single post component
 */
function Post({ post, onClick, onHashtagClick, agentName }) {
    const [zoomedImage, setZoomedImage] = useState(null);
    const contentRef = useRef(null);
    
    const data = post.data;
    const isAgent = data.type === 'agent_response';
    const displayName = isAgent ? (agentName || 'Agent') : 'You';
    
    // Get avatar info based on the name
    const avatarInfo = isAgent ? getAvatarInfo(agentName) : getAvatarInfo('You');
    
    // Remove URLs that have previews from the displayed content
    const displayContent = removePreviewedUrls(data.content, data.link_previews);
    
    // Render mermaid diagrams after content is mounted
    useEffect(() => {
        if (contentRef.current) {
            renderMermaidDiagrams(contentRef.current);
        }
    }, [displayContent]);
    
    const handleImageClick = (e, mediaId) => {
        e.stopPropagation();
        setZoomedImage(getMediaUrl(mediaId));
    };
    
    // Separate images from files using content_blocks info
    const imageItems = [];
    const fileIds = [];
    const resourceLinks = [];
    const resources = [];
    const textAnnotations = [];
    const blocks = data.content_blocks || [];
    const mediaIds = data.media_ids || [];
    let mediaIndex = 0;
    
    if (blocks.length > 0) {
        blocks.forEach((block) => {
            if (block?.type === 'text' && block.annotations) {
                textAnnotations.push(block.annotations);
            }
            if (block?.type === 'resource_link') {
                resourceLinks.push(block);
            } else if (block?.type === 'resource') {
                resources.push(block);
            } else if (block?.type === 'file') {
                const id = mediaIds[mediaIndex++];
                if (id) fileIds.push(id);
            } else if (block?.type === 'image' || !block?.type) {
                const id = mediaIds[mediaIndex++];
                if (id) imageItems.push({ id, annotations: block?.annotations });
            }
        });
    } else if (mediaIds.length > 0) {
        mediaIds.forEach((id) => imageItems.push({ id, annotations: null }));
    }
    
    return html`
        <div id=${`post-${post.id}`} class="post ${isAgent ? 'agent-post' : ''}" onClick=${onClick}>
            <div class="post-avatar ${isAgent ? 'agent-avatar' : ''}" style="background-color: ${avatarInfo.color}">
                ${avatarInfo.letter}
            </div>
            <div class="post-body">
                <div class="post-meta">
                    <span class="post-author">${displayName}</span>
                    <span class="post-time">${formatTime(post.timestamp)}</span>
                </div>
                ${displayContent && html`
                    <div 
                        ref=${contentRef}
                        class="post-content"
                        dangerouslySetInnerHTML=${{ __html: renderMarkdown(displayContent, onHashtagClick) }}
                        onClick=${(e) => {
                            if (e.target.classList.contains('hashtag')) {
                                e.preventDefault();
                                e.stopPropagation();
                                const tag = e.target.dataset.hashtag;
                                if (tag) onHashtagClick?.(tag);
                            } else if (e.target.tagName === 'IMG') {
                                e.preventDefault();
                                e.stopPropagation();
                                setZoomedImage(e.target.src);
                            }
                        }}
                    />
                `}
                ${textAnnotations.length > 0 && html`
                    ${textAnnotations.map((annotations, idx) => html`
                        <${AnnotationsBadge} key=${idx} annotations=${annotations} />
                    `)}
                `}
                ${imageItems.length > 0 && html`
                    <div class="media-preview">
                        ${imageItems.map(({ id }) => html`
                            <img 
                                key=${id} 
                                src=${getThumbnailUrl(id)} 
                                alt="Media" 
                                loading="lazy"
                                onClick=${(e) => handleImageClick(e, id)}
                            />
                        `)}
                    </div>
                `}
                ${imageItems.length > 0 && html`
                    ${imageItems.map(({ annotations }, idx) => html`
                        ${annotations && html`<${AnnotationsBadge} key=${idx} annotations=${annotations} />`}
                    `)}
                `}
                ${fileIds.length > 0 && html`
                    <div class="file-attachments">
                        ${fileIds.map(id => html`
                            <${FileAttachment} key=${id} mediaId=${id} />
                        `)}
                    </div>
                `}
                ${resourceLinks.length > 0 && html`
                    <div class="resource-links">
                        ${resourceLinks.map((block, idx) => html`
                            <div key=${idx}>
                                <${ResourceLinkBlock} block=${block} />
                                <${AnnotationsBadge} annotations=${block.annotations} />
                            </div>
                        `)}
                    </div>
                `}
                ${resources.length > 0 && html`
                    <div class="resource-embeds">
                        ${resources.map((block, idx) => html`
                            <div key=${idx}>
                                <${ResourceBlock} block=${block} />
                                <${AnnotationsBadge} annotations=${block.annotations} />
                            </div>
                        `)}
                    </div>
                `}
                ${data.link_previews?.length > 0 && html`
                    <div class="link-previews">
                        ${data.link_previews.map((preview, i) => html`
                            <${LinkPreview} key=${i} preview=${preview} />
                        `)}
                    </div>
                `}
            </div>
        </div>
        ${zoomedImage && html`<${ImageModal} src=${zoomedImage} onClose=${() => setZoomedImage(null)} />`}
    `;
}

/**
 * Timeline component (chat style - uses column-reverse for smooth prepending)
 */
function Timeline({ posts, hasMore, onLoadMore, onPostClick, onHashtagClick, emptyMessage, timelineRef, agents, reverse = true }) {
    const [loadingMore, setLoadingMore] = useState(false);
    
    const handleScroll = useCallback(async (e) => {
        if (!reverse || !onLoadMore) return;
        const { scrollTop, scrollHeight, clientHeight } = e.target;
        // In column-reverse, scrollTop is negative or we check distance from "top" (which is visual bottom)
        // scrollTop of 0 means we're at the bottom, negative means scrolled up
        // We want to load more when near the visual top (which is scrollHeight - clientHeight - |scrollTop|)
        const distanceFromTop = scrollHeight - clientHeight + scrollTop;
        const prefetchThreshold = Math.max(300, clientHeight);
        
        if (distanceFromTop < prefetchThreshold && hasMore && !loadingMore && onLoadMore) {
            setLoadingMore(true);
            await onLoadMore();
            setLoadingMore(false);
        }
    }, [hasMore, loadingMore, onLoadMore, reverse]);
    
    if (!posts) {
        return html`<div class="loading"><div class="spinner"></div></div>`;
    }
    
    if (posts.length === 0) {
        return html`
            <div class="timeline" ref=${timelineRef}>
                <div class="timeline-content">
                    <div style="padding: var(--spacing-xl); text-align: center; color: var(--text-secondary)">
                        ${emptyMessage || 'No messages yet. Start a conversation!'}
                    </div>
                </div>
            </div>
        `;
    }
    
    // Sort posts by id (oldest first) for reverse (chat-style) view
    const displayPosts = reverse ? posts.slice().sort((a, b) => a.id - b.id) : posts;
    
    return html`
        <div class="timeline ${reverse ? 'reverse' : 'normal'}" ref=${timelineRef} onScroll=${handleScroll}>
            <div class="timeline-content">
                ${hasMore && html`
                    <button class="load-more-btn" onClick=${onLoadMore} disabled=${loadingMore}>
                        ${loadingMore ? 'Loading...' : 'Load older messages'}
                    </button>
                `}
                ${displayPosts.map(post => html`
                    <${Post}
                        key=${post.id}
                        post=${post}
                        agentName=${getAgentName(post.data?.agent_id, agents)}
                        onClick=${() => onPostClick?.(post)}
                        onHashtagClick=${onHashtagClick}
                    />
                `)}
            </div>
        </div>
    `;
}

/**
 * Agent status indicator
 */
function AgentStatus({ status, draft, plan, thought }) {
    if (!status && !draft && !plan && !thought) return null;

    const DRAFT_MAX_CHARS = 2048;
    const DRAFT_TAIL_CHARS = 256;

    const truncateDraft = (text) => {
        const value = text || '';
        if (value.length <= DRAFT_MAX_CHARS) return { text: value, omitted: 0 };
        const headLen = Math.max(0, DRAFT_MAX_CHARS - DRAFT_TAIL_CHARS);
        const head = value.slice(0, headLen);
        const tail = value.slice(-DRAFT_TAIL_CHARS);
        const omitted = value.length - head.length - tail.length;
        return { text: `${head}\n…\n${tail}`, omitted };
    };
    
    let content = '';
    const title = status?.title;
    const statusText = status?.status;
    if (status?.type === 'plan') {
        content = title ? `Planning: ${title}` : 'Planning...';
    } else if (status?.type === 'tool_call') {
        content = title ? `Running: ${title}` : 'Running tool...';
    } else if (status?.type === 'tool_status') {
        content = title ? `${title}: ${statusText || 'Working...'}` : (statusText || 'Working...');
    } else {
        content = title || statusText || 'Working...';
    }
    
    return html`
        <div class="agent-status-panel">
            ${plan && html`
                <div class="agent-thinking">
                    <div class="agent-thinking-title">Planning</div>
                    <div
                        class="agent-thinking-body"
                        dangerouslySetInnerHTML=${{ __html: renderThinkingMarkdown(plan) }}
                    />
                </div>
            `}
            ${thought && html`
                <div class="agent-thinking">
                    <div class="agent-thinking-title thought">Thoughts</div>
                    <div
                        class="agent-thinking-body"
                        dangerouslySetInnerHTML=${{ __html: renderThinkingMarkdown(thought) }}
                    />
                </div>
            `}
            ${draft && (() => {
                const truncated = truncateDraft(draft);
                return html`
                    <div class="agent-thinking">
                        <div class="agent-thinking-title thought">Draft</div>
                        <div
                            class="agent-thinking-body"
                            dangerouslySetInnerHTML=${{ __html: renderThinkingMarkdown(truncated.text) }}
                        />
                        ${truncated.omitted > 0 && html`
                            <div class="agent-thinking-truncation">(${truncated.omitted} more characters)</div>
                        `}
                    </div>
                `;
            })()}
            ${status && html`
                <div class="agent-status">
                    <div class="agent-status-spinner"></div>
                    <span class="agent-status-text">${content}</span>
                </div>
            `}
        </div>
    `;
}

/**
 * Agent request modal - shows permission/choice requests from agent
 */
function AgentRequestModal({ request, onRespond }) {
    if (!request) return null;
    
    const { request_id, tool_call, options } = request;
    const title = tool_call?.title || 'Agent Request';
    const kind = tool_call?.kind || 'other';
    
    // Extract command and explanation from tool call metadata
    const rawInput = tool_call?.rawInput || {};
    const command = rawInput.command || (rawInput.commands && rawInput.commands[0]) || null;
    const diff = rawInput.diff || null;
    const fileName = rawInput.fileName || rawInput.path || null;
    const explanation = tool_call?.description || rawInput.description || rawInput.explanation || null;
    const locations = Array.isArray(tool_call?.locations) ? tool_call.locations : [];
    const locationPaths = locations
        .map((loc) => loc?.path)
        .filter((path) => Boolean(path));
    const uniquePaths = Array.from(new Set([fileName, ...locationPaths].filter(Boolean)));
    
    console.log('AgentRequestModal:', { request_id, tool_call, options });
    
    const handleResponse = async (outcome) => {
        try {
            await respondToAgentRequest(request_id, outcome);
            onRespond();
        } catch (e) {
            console.error('Failed to respond to agent request:', e);
        }
    };
    
    const handleAlwaysAllow = async () => {
        try {
            // Add to whitelist with the exact title
            await addToWhitelist(title, `Auto-approved: ${title}`);
            // Then approve this request
            await respondToAgentRequest(request_id, 'approved');
            onRespond();
        } catch (e) {
            console.error('Failed to add to whitelist:', e);
        }
    };
    
    // ACP options format: { optionId, name, kind }
    const hasOptions = options && options.length > 0;
    
    return html`
        <div class="agent-request-modal">
            <div class="agent-request-content">
                <div class="agent-request-header">
                    <div class="agent-request-icon">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                    </div>
                    <div class="agent-request-title">${title}</div>
                </div>
                ${(explanation || command || diff || uniquePaths.length > 0) && html`
                    <div class="agent-request-body">
                        ${explanation && html`
                            <div class="agent-request-description">${explanation}</div>
                        `}
                        ${uniquePaths.length > 0 && html`
                            <div class="agent-request-files">
                                <div class="agent-request-subtitle">Files</div>
                                <ul>
                                    ${uniquePaths.map((path, idx) => html`<li key=${idx}>${path}</li>`)}
                                </ul>
                            </div>
                        `}
                        ${command && html`
                            <pre class="agent-request-command">${command}</pre>
                        `}
                        ${diff && html`
                            <details class="agent-request-diff">
                                <summary>Proposed diff</summary>
                                <pre>${diff}</pre>
                            </details>
                        `}
                    </div>
                `}
                <div class="agent-request-actions">
                    ${hasOptions ? (
                        options.map(opt => html`
                            <button 
                                key=${opt.optionId || opt.id || String(opt)}
                                class="agent-request-btn ${opt.kind === 'allow_once' || opt.kind === 'allow_always' ? 'primary' : ''}"
                                onClick=${() => handleResponse(opt.optionId || opt.id || opt)}
                            >
                                ${opt.name || opt.label || opt.optionId || opt.id || String(opt)}
                            </button>
                        `)
                    ) : html`
                        <button class="agent-request-btn primary" onClick=${() => handleResponse('approved')}>
                            Allow
                        </button>
                        <button class="agent-request-btn" onClick=${() => handleResponse('denied')}>
                            Deny
                        </button>
                        <button class="agent-request-btn always-allow" onClick=${handleAlwaysAllow}>
                            Always Allow This
                        </button>
                    `}
                </div>
            </div>
        </div>
    `;
}

/**
 * Connection status indicator
 */
function ConnectionStatus({ status }) {
    if (status === 'connected') return null;
    
    return html`
        <div class="connection-status ${status}">
            ${status === 'disconnected' ? 'Reconnecting...' : status}
        </div>
    `;
}

/**
 * Main App component
 */
function App() {
    const [posts, setPosts] = useState(null);
    const [hasMore, setHasMore] = useState(false);
    const [connectionStatus, setConnectionStatus] = useState('disconnected');
    const [currentHashtag, setCurrentHashtag] = useState(null);
    const [searchQuery, setSearchQuery] = useState(null);
    const [searchOpen, setSearchOpen] = useState(false);
    const [agentStatus, setAgentStatus] = useState(null);
    const [agentDraft, setAgentDraft] = useState('');
    const [agentPlan, setAgentPlan] = useState('');
    const [agentThought, setAgentThought] = useState('');
    const [pendingRequest, setPendingRequest] = useState(null);
    const [agents, setAgents] = useState({});
    const [pendingScrollId, setPendingScrollId] = useState(null);
    const timelineRef = useRef(null);
    const navigatingRef = useRef(false);
    
    // Refresh timestamps every 30 seconds
    useTimestampRefresh(30000);
    
    // Scroll to bottom of timeline (with column-reverse, scrollTop=0 is bottom)
    const scrollToBottom = useCallback(() => {
        if (timelineRef.current) {
            timelineRef.current.scrollTop = 0;
        }
    }, []);
    
    // Load timeline or hashtag posts
    const loadPosts = useCallback(async (hashtag = null) => {
        try {
            if (hashtag) {
                const result = await getPostsByHashtag(hashtag);
                setPosts(result.posts);
                setHasMore(false);
            } else {
                const result = await getTimeline(10);
                setPosts(result.posts);
                setHasMore(result.has_more);
            }
        } catch (error) {
            console.error('Failed to load posts:', error);
        }
    }, []);
    
    // Load older messages - with column-reverse, browser handles scroll anchoring automatically
    const loadMore = useCallback(async () => {
        if (!posts || posts.length === 0) return;
        
        // Find oldest post id
        const sortedPosts = posts.slice().sort((a, b) => a.id - b.id);
        const oldestId = sortedPosts[0].id;
        
        console.log('Loading more before id:', oldestId);
        try {
            const result = await getTimeline(5, oldestId);
            console.log('Loaded:', result.posts.length, 'has_more:', result.has_more);
            if (result.posts.length > 0) {
                // Simply prepend - column-reverse handles scroll position
                setPosts(prev => [...result.posts, ...prev]);
                setHasMore(result.has_more);
            } else {
                setHasMore(false);
            }
        } catch (error) {
            console.error('Failed to load more posts:', error);
        }
    }, [posts, timelineRef]);
    
    // Handle hashtag click
    const handleHashtagClick = useCallback(async (hashtag) => {
        setCurrentHashtag(hashtag);
        setPosts(null); // Show loading
        try {
            const result = await getPostsByHashtag(hashtag);
            setPosts(result.posts);
            setHasMore(false);
        } catch (error) {
            console.error('Failed to load hashtag posts:', error);
        }
    }, []);
    
    // Go back to timeline
    const handleBackToTimeline = useCallback(async () => {
        setCurrentHashtag(null);
        setSearchQuery(null);
        setPosts(null);
        try {
            const result = await getTimeline(10);
            setPosts(result.posts);
            setHasMore(result.has_more);
        } catch (error) {
            console.error('Failed to load timeline:', error);
        }
    }, []);

    // Handle search
    const handleSearch = useCallback(async (query) => {
        if (!query || !query.trim()) return;
        setSearchQuery(query.trim());
        setCurrentHashtag(null);
        setPosts(null);
        try {
            const result = await searchPosts(query.trim());
            setPosts(result.results);
            setHasMore(false);
        } catch (error) {
            console.error('Failed to search:', error);
            setPosts([]);
        }
    }, []);
    
    const enterSearchMode = useCallback(() => {
        setSearchOpen(true);
        setSearchQuery(null);
        setCurrentHashtag(null);
        setPosts([]);
    }, []);
    
    const exitSearchMode = useCallback(() => {
        setSearchOpen(false);
        setSearchQuery(null);
        loadPosts();
    }, [loadPosts]);

    const scrollToPost = useCallback((postId) => {
        const element = document.getElementById(`post-${postId}`);
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, []);

    const navigateToSearchResult = useCallback(async (postId) => {
        if (!postId) return;
        setSearchOpen(false);
        setSearchQuery(null);
        setCurrentHashtag(null);
        setPendingScrollId(postId);
        setPosts(null);
        loadPosts();
    }, [loadPosts]);

    useEffect(() => {
        if (!pendingScrollId || searchQuery || currentHashtag) return;
        if (!posts || posts.length === 0) return;
        const element = document.getElementById(`post-${pendingScrollId}`);
        if (element) {
            scrollToPost(pendingScrollId);
            setPendingScrollId(null);
            return;
        }
        if (!hasMore || navigatingRef.current) return;
        const loadOlder = async () => {
            navigatingRef.current = true;
            try {
                const sortedPosts = posts.slice().sort((a, b) => a.id - b.id);
                const oldestId = sortedPosts[0]?.id;
                if (!oldestId) return;
                const older = await getTimeline(10, oldestId);
                if (older.posts.length === 0) return;
                setPosts((prev) => [...older.posts, ...(prev || [])]);
                setHasMore(older.has_more);
            } catch (error) {
                console.error('Failed to load older posts for navigation:', error);
            } finally {
                navigatingRef.current = false;
            }
        };
        loadOlder();
    }, [pendingScrollId, searchQuery, currentHashtag, posts, hasMore, scrollToPost]);

    useEffect(() => {
        getAgents()
            .then((data) => {
                const map = {};
                (data.agents || []).forEach((agent) => {
                    map[agent.id] = agent;
                });
                setAgents(map);
            })
            .catch((e) => console.warn('Failed to load agents:', e));
    }, []);
    
    useEffect(() => {
        getAgents()
            .then((data) => {
                const map = {};
                (data.agents || []).forEach((agent) => {
                    map[agent.id] = agent;
                });
                setAgents(map);
            })
            .catch((e) => console.warn('Failed to load agents:', e));
    }, []);

    // Set up SSE connection
    useEffect(() => {
        loadPosts();
        
        const sse = new SSEClient(
            (eventType, data) => {
                // Handle agent status updates
                if (eventType === 'agent_status') {
                    console.log('Agent status:', data);
                    if (data.type === 'done' || data.type === 'error') {
                        setAgentStatus(null);
                        setAgentDraft('');
                        setAgentPlan('');
                        setAgentThought('');
                    } else {
                        setAgentStatus(data);
                    }
                    return;
                }

                if (eventType === 'agent_draft') {
                    const text = data.text || '';
                    const mode = data.mode || (data.kind === 'plan' ? 'replace' : 'append');

                    if (data.kind === 'plan') {
                        if (mode === 'replace') setAgentPlan(text);
                        else setAgentPlan((prev) => (prev || '') + text);
                    } else {
                        if (mode === 'replace') setAgentDraft(text);
                        else setAgentDraft((prev) => (prev || '') + text);
                    }
                    return;
                }
                
                if (eventType === 'agent_thought') {
                    // Thoughts tend to be sent as snapshots.
                    setAgentThought(data.text || '');
                    return;
                }
                
                // Handle agent requests (permission, choices)
                if (eventType === 'agent_request') {
                    console.log('Agent request:', data);
                    setPendingRequest(data);
                    return;
                }

                if (eventType === 'agent_request_timeout') {
                    console.log('Agent request timeout:', data);
                    setPendingRequest(null);
                    setAgentStatus({ type: 'error', title: 'Permission request timed out' });
                    return;
                }
                
                // Add new posts/replies to timeline (only when on main timeline) - append at end for chat style
                if (!currentHashtag && (eventType === 'new_post' || eventType === 'agent_response')) {
                    setPosts(prev => prev ? [...prev, data] : [data]);
                    // With column-reverse, new items at end appear at visual bottom automatically
                }
                // Update existing post (e.g., when link previews are fetched)
                if (eventType === 'interaction_updated') {
                    setPosts(prev => prev ? prev.map(p => p.id === data.id ? data : p) : prev);
                }
                
            },
            setConnectionStatus
        );
        
        sse.connect();
        
        return () => sse.disconnect();
    }, [loadPosts]);
    
    return html`
        <div class="container">
            ${searchQuery && isIOSDevice() && html`<div class="search-results-spacer"></div>`}
            ${(currentHashtag || searchQuery) && html`
                <div class="hashtag-header">
                    <button class="back-btn" onClick=${handleBackToTimeline}>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                    </button>
                    <span>${currentHashtag ? `#${currentHashtag}` : `Search: ${searchQuery}`}</span>
                </div>
            `}
            <${Timeline} 
                posts=${posts}
                hasMore=${hasMore}
                onLoadMore=${loadMore}
                timelineRef=${timelineRef}
                onHashtagClick=${handleHashtagClick}
                onPostClick=${searchQuery ? (post) => navigateToSearchResult(post.id) : undefined}
                emptyMessage=${currentHashtag ? `No posts with #${currentHashtag}` : searchQuery ? `No results for "${searchQuery}"` : undefined}
                agents=${agents}
                reverse=${!(searchQuery && !currentHashtag)}
            />
            <${AgentStatus} status=${agentStatus} draft=${agentDraft} plan=${agentPlan} thought=${agentThought} />
            <${ComposeBox} 
                onPost=${() => { loadPosts(); }}
                onFocus=${scrollToBottom}
                searchMode=${searchOpen}
                onSearch=${handleSearch}
                onEnterSearch=${enterSearchMode}
                onExitSearch=${exitSearchMode}
            />
            <${ConnectionStatus} status=${connectionStatus} />
            <${AgentRequestModal} request=${pendingRequest} onRespond=${() => setPendingRequest(null)} />
        </div>
    `;
}

// Mount the app
render(html`<${App} />`, document.getElementById('app'));
