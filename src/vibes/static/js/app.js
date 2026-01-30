import { html, render, useState, useEffect, useCallback, useRef } from './vendor/preact-htm.js';
import { getTimeline, getPostsByHashtag, getThread, createPost, sendAgentMessage, uploadMedia, getThumbnailUrl, getMediaUrl, SSEClient } from './api.js';

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
    
    // Process hashtags - wrap them in clickable spans (will be handled by event delegation)
    html_content = html_content.replace(HASHTAG_REGEX, '<a href="#" class="hashtag" data-hashtag="$1">#$1</a>');
    
    return html_content;
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
 * Request notification permission
 */
async function requestNotificationPermission() {
    if (!('Notification' in window)) {
        console.log('Notifications not supported');
        return false;
    }
    
    if (Notification.permission === 'granted') {
        return true;
    }
    
    if (Notification.permission !== 'denied') {
        const permission = await Notification.requestPermission();
        return permission === 'granted';
    }
    
    return false;
}

/**
 * Show desktop notification
 */
function showNotification(title, body, onClick) {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    
    const notification = new Notification(title, {
        body: body,
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        tag: 'vibes-notification',
        renotify: true
    });
    
    notification.onclick = () => {
        window.focus();
        notification.close();
        onClick?.();
    };
}

/**
 * Check if content mentions user with @
 */
function hasMention(content) {
    // Match @user, @me, @you or similar patterns
    return /@\w+/i.test(content);
}

/**
 * Get avatar letter from type
 */
function getAvatarLetter(type) {
    if (type === 'agent_response') return 'A';
    return 'U';
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
 * Theme toggle component
 */
function ThemeToggle() {
    const [dark, setDark] = useState(() => {
        const stored = localStorage.getItem('theme');
        if (stored) return stored === 'dark';
        return window.matchMedia('(prefers-color-scheme: dark)').matches;
    });
    
    useEffect(() => {
        document.body.classList.toggle('dark', dark);
        document.body.classList.toggle('light', !dark);
        localStorage.setItem('theme', dark ? 'dark' : 'light');
        updateThemeColor(dark);
    }, [dark]);
    
    // Set initial theme color
    useEffect(() => {
        updateThemeColor(dark);
    }, []);
    
    return html`
        <button class="theme-toggle floating-btn" onClick=${() => setDark(!dark)} title="Toggle theme">
            ${dark ? html`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>` : html`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`}
        </button>
    `;
}

/**
 * Compose box component
 */
function ComposeBox({ onPost, onFocus }) {
    const [content, setContent] = useState('');
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
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            handleSubmit();
        }
    };
    
    const handleFileChange = (e) => {
        setMediaFiles([...e.target.files]);
    };
    
    // Auto-resize textarea
    const handleInput = (e) => {
        setContent(e.target.value);
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
                    placeholder="Message..."
                    value=${content}
                    onInput=${handleInput}
                    onKeyDown=${handleKeyDown}
                    onFocus=${onFocus}
                    disabled=${loading}
                    rows="1"
                />
                <div class="compose-actions">
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
function Post({ post, onClick, onHashtagClick }) {
    const [zoomedImage, setZoomedImage] = useState(null);
    
    const data = post.data;
    const isAgent = data.type === 'agent_response';
    const staggerClass = post._stagger !== undefined ? `staggered-${post._stagger}` : '';
    const insertingClass = post._inserting ? 'inserting' : '';
    
    // Remove URLs that have previews from the displayed content
    const displayContent = removePreviewedUrls(data.content, data.link_previews);
    
    const handleImageClick = (e, mediaId) => {
        e.stopPropagation();
        setZoomedImage(getMediaUrl(mediaId));
    };
    
    return html`
        <div class="post ${isAgent ? 'agent-post' : ''} ${staggerClass} ${insertingClass}" onClick=${onClick}>
            <div class="post-avatar" style=${isAgent ? 'background-color: #00ba7c' : ''}>
                ${getAvatarLetter(data.type)}
            </div>
            <div class="post-body">
                <div class="post-meta">
                    <span class="post-author">${isAgent ? 'Agent' : 'You'}</span>
                    <span class="post-time">${formatTime(post.timestamp)}</span>
                </div>
                ${displayContent && html`
                    <div 
                        class="post-content"
                        dangerouslySetInnerHTML=${{ __html: renderMarkdown(displayContent, onHashtagClick) }}
                        onClick=${(e) => {
                            if (e.target.classList.contains('hashtag')) {
                                e.preventDefault();
                                e.stopPropagation();
                                const tag = e.target.dataset.hashtag;
                                if (tag) onHashtagClick?.(tag);
                            }
                        }}
                    />
                `}
                ${data.media_ids?.length > 0 && html`
                    <div class="media-preview">
                        ${data.media_ids.map(id => html`
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
 * Timeline component (chat style - scrolls to bottom, loads older on scroll up)
 */
function Timeline({ posts, hasMore, onLoadMore, onPostClick, onHashtagClick, emptyMessage, timelineRef }) {
    const [loadingMore, setLoadingMore] = useState(false);
    
    const handleScroll = useCallback(async (e) => {
        const { scrollTop, clientHeight } = e.target;
        // Prefetch when within 1 viewport height of the top
        const prefetchThreshold = Math.max(300, clientHeight);
        if (scrollTop < prefetchThreshold && hasMore && !loadingMore && onLoadMore) {
            setLoadingMore(true);
            await onLoadMore();
            setLoadingMore(false);
        }
    }, [hasMore, loadingMore, onLoadMore]);
    
    if (!posts) {
        return html`<div class="loading"><div class="spinner"></div></div>`;
    }
    
    if (posts.length === 0) {
        return html`
            <div class="timeline" ref=${timelineRef}>
                <div style="padding: var(--spacing-xl); text-align: center; color: var(--text-secondary)">
                    ${emptyMessage || 'No messages yet. Start a conversation!'}
                </div>
            </div>
        `;
    }
    
    return html`
        <div class="timeline" ref=${timelineRef} onScroll=${handleScroll}>
            ${loadingMore && html`<div class="loading"><div class="spinner"></div></div>`}
            ${hasMore && !loadingMore && html`
                <button class="load-more-btn" onClick=${onLoadMore}>Load older messages</button>
            `}
            ${posts.slice().sort((a, b) => a.id - b.id).map(post => html`
                <${Post} key=${post.id} post=${post} onClick=${() => onPostClick?.(post)} onHashtagClick=${onHashtagClick} />
            `)}
        </div>
    `;
}

/**
 * Agent status indicator
 */
function AgentStatus({ status }) {
    if (!status) return null;
    
    return html`
        <div class="agent-status">
            <div class="agent-status-spinner"></div>
            <span class="agent-status-text">${status.title || 'Working...'}</span>
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
    const [notificationsEnabled, setNotificationsEnabled] = useState(
        typeof Notification !== 'undefined' && Notification.permission === 'granted'
    );
    const [agentStatus, setAgentStatus] = useState(null);
    const timelineRef = useRef(null);
    
    // Refresh timestamps every 30 seconds
    useTimestampRefresh(30000);
    
    // Scroll to bottom of timeline
    const scrollToBottom = useCallback(() => {
        if (timelineRef.current) {
            timelineRef.current.scrollTop = timelineRef.current.scrollHeight;
        }
    }, []);
    
    // Request notification permission on first interaction
    const enableNotifications = useCallback(async () => {
        const granted = await requestNotificationPermission();
        setNotificationsEnabled(granted);
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
                // Scroll to bottom after initial load
                setTimeout(scrollToBottom, 100);
            }
        } catch (error) {
            console.error('Failed to load posts:', error);
        }
    }, [scrollToBottom]);
    
    // Load older messages
    const loadMore = useCallback(async () => {
        if (!posts || posts.length === 0) return;
        
        const oldestId = posts[0].id;
        console.log('Loading more before id:', oldestId);
        try {
            const result = await getTimeline(3, oldestId);
            console.log('Loaded:', result.posts.length, 'has_more:', result.has_more);
            if (result.posts.length > 0) {
                const timeline = timelineRef.current;
                
                // Save scroll metrics before DOM changes
                const scrollHeightBefore = timeline?.scrollHeight || 0;
                const scrollTopBefore = timeline?.scrollTop || 0;
                
                // Add posts with stagger index and inserting flag
                const staggeredPosts = result.posts.map((post, i) => ({
                    ...post,
                    _stagger: result.posts.length - 1 - i,
                    _inserting: true
                }));
                
                const newIds = new Set(result.posts.map(p => p.id));
                setPosts(prev => [...staggeredPosts, ...prev]);
                setHasMore(result.has_more);
                
                // Use setTimeout to ensure React has flushed DOM updates
                setTimeout(() => {
                    if (timeline) {
                        // Calculate how much content was added
                        const scrollHeightAfter = timeline.scrollHeight;
                        const addedHeight = scrollHeightAfter - scrollHeightBefore;
                        
                        // Adjust scroll to maintain visual position
                        timeline.scrollTop = scrollTopBefore + addedHeight;
                        
                        // Reveal items after scroll is committed
                        requestAnimationFrame(() => {
                            setPosts(prev => prev.map(p => {
                                if (newIds.has(p.id)) {
                                    const { _inserting, ...rest } = p;
                                    return rest;
                                }
                                return p;
                            }));
                        });
                    }
                }, 0);
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
        setPosts(null);
        try {
            const result = await getTimeline(10);
            setPosts(result.posts);
            setHasMore(result.has_more);
            setTimeout(scrollToBottom, 100);
        } catch (error) {
            console.error('Failed to load timeline:', error);
        }
    }, [scrollToBottom]);
    
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
                    } else {
                        setAgentStatus(data);
                    }
                    return;
                }
                
                // Add new posts/replies to timeline (only when on main timeline) - append at end for chat style
                if (!currentHashtag && (eventType === 'new_post' || eventType === 'agent_response')) {
                    setPosts(prev => prev ? [...prev, data] : [data]);
                    // Scroll to bottom for new messages
                    setTimeout(scrollToBottom, 100);
                }
                // Update existing post (e.g., when link previews are fetched)
                if (eventType === 'interaction_updated') {
                    setPosts(prev => prev ? prev.map(p => p.id === data.id ? data : p) : prev);
                }
                
                // Show notifications for replies and mentions (only when window not focused)
                if (document.hidden && notificationsEnabled) {
                    const content = data.data?.content || '';
                    const isReply = eventType === 'new_reply' || data.data?.thread_id;
                    const isAgentResponse = eventType === 'agent_response';
                    const hasMentionInContent = hasMention(content);
                    
                    if (isReply || isAgentResponse || hasMentionInContent) {
                        const author = isAgentResponse ? 'Agent' : 'Reply';
                        const title = hasMentionInContent ? `${author} mentioned you` : `New ${author.toLowerCase()}`;
                        const body = content.length > 100 ? content.substring(0, 100) + '...' : content;
                        showNotification(title, body);
                    }
                }
            },
            setConnectionStatus
        );
        
        sse.connect();
        
        return () => sse.disconnect();
    }, [loadPosts, notificationsEnabled]);
    
    return html`
        <div class="container">
            <div class="floating-controls">
                <button 
                    class="floating-btn ${notificationsEnabled ? 'enabled' : ''}" 
                    onClick=${enableNotifications}
                    title=${notificationsEnabled ? 'Notifications enabled' : 'Enable notifications'}
                >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
                        <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
                        ${!notificationsEnabled && html`<line x1="1" y1="1" x2="23" y2="23"/>`}
                    </svg>
                </button>
                <${ThemeToggle} />
            </div>
            ${currentHashtag && html`
                <div class="hashtag-header">
                    <button class="back-btn" onClick=${handleBackToTimeline}>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                    </button>
                    <span>#${currentHashtag}</span>
                </div>
            `}
            <${Timeline} 
                posts=${posts}
                hasMore=${hasMore}
                onLoadMore=${loadMore}
                timelineRef=${timelineRef}
                onHashtagClick=${handleHashtagClick}
                emptyMessage=${currentHashtag ? `No posts with #${currentHashtag}` : undefined}
            />
            <${AgentStatus} status=${agentStatus} />
            ${!currentHashtag && html`<${ComposeBox} onPost=${() => { loadPosts(); }} onFocus=${scrollToBottom} />`}
            <${ConnectionStatus} status=${connectionStatus} />
        </div>
    `;
}

// Mount the app
render(html`<${App} />`, document.getElementById('app'));
