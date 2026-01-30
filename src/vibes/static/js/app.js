import { html, render, useState, useEffect, useCallback, useRef } from './vendor/preact-htm.js';
import { getTimeline, getPostsByHashtag, createPost, sendAgentMessage, uploadMedia, getThumbnailUrl, SSEClient } from './api.js';

// URL regex for linkifying text
const URL_REGEX = /(https?:\/\/[^\s<>"{}|\\^`\[\]]+)/g;
// Hashtag regex
const HASHTAG_REGEX = /#(\w+)/g;

/**
 * Linkify text - convert URLs and hashtags to clickable elements
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
    if (Notification.permission !== 'granted') return;
    
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
    }, [dark]);
    
    return html`
        <button class="theme-toggle" onClick=${() => setDark(!dark)} title="Toggle theme">
            ${dark ? html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>` : html`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`}
        </button>
    `;
}

/**
 * Compose box component
 */
function ComposeBox({ onPost }) {
    const [content, setContent] = useState('');
    const [loading, setLoading] = useState(false);
    const [mediaFiles, setMediaFiles] = useState([]);
    
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
    
    return html`
        <div class="compose-box">
            <textarea
                placeholder="What's happening?"
                value=${content}
                onInput=${(e) => setContent(e.target.value)}
                onKeyDown=${handleKeyDown}
                disabled=${loading}
            />
            ${mediaFiles.length > 0 && html`
                <div class="media-preview">
                    ${mediaFiles.map(f => html`<span key=${f.name}>${f.name} </span>`)}
                </div>
            `}
            <div class="compose-actions">
                <div class="compose-actions-left">
                    <label class="icon-btn" title="Attach image">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                        <input type="file" accept="image/*" multiple hidden onChange=${handleFileChange} />
                    </label>
                </div>
                <button 
                    class="post-btn" 
                    onClick=${handleSubmit}
                    disabled=${loading || (!content.trim() && mediaFiles.length === 0)}
                >
                    ${loading ? '...' : 'Post'}
                </button>
            </div>
        </div>
    `;
}

/**
 * Link preview component - Twitter-style card with image background
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
 * Remove URLs from text that have previews
 */
function removePreviewedUrls(text, linkPreviews) {
    if (!linkPreviews?.length) return text;
    
    let result = text;
    for (const preview of linkPreviews) {
        // Remove the URL (and any trailing whitespace/newline)
        result = result.replace(new RegExp(preview.url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*', 'g'), '');
    }
    return result.trim();
}

/**
 * Single post component
 */
function Post({ post, onClick, onHashtagClick }) {
    const data = post.data;
    const isAgent = data.type === 'agent_response';
    
    // Remove URLs that have previews from the displayed content
    const displayContent = removePreviewedUrls(data.content, data.link_previews);
    
    return html`
        <div class="post" onClick=${onClick}>
            <div class="post-header">
                <div class="post-avatar" style=${isAgent ? 'background-color: #00ba7c' : ''}>
                    ${getAvatarLetter(data.type)}
                </div>
                <div class="post-meta">
                    <span class="post-author">${isAgent ? 'Agent' : 'You'}</span>
                    <span class="post-time">${formatTime(post.timestamp)}</span>
                </div>
            </div>
            ${displayContent && html`
                <div class="post-content ${isAgent ? 'agent' : ''}">
                    ${linkifyContent(displayContent, onHashtagClick)}
                </div>
            `}
            ${data.media_ids?.length > 0 && html`
                <div class="media-preview">
                    ${data.media_ids.map(id => html`
                        <img key=${id} src=${getThumbnailUrl(id)} alt="Media" loading="lazy" />
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
    `;
}

/**
 * Timeline component
 */
function Timeline({ posts, onPostClick, onHashtagClick, emptyMessage }) {
    if (!posts) {
        return html`<div class="loading"><div class="spinner"></div></div>`;
    }
    
    if (posts.length === 0) {
        return html`
            <div style="padding: var(--spacing-xl); text-align: center; color: var(--text-secondary)">
                ${emptyMessage || 'No posts yet. Start a conversation!'}
            </div>
        `;
    }
    
    return html`
        <div class="timeline">
            ${posts.map(post => html`
                <${Post} key=${post.id} post=${post} onClick=${() => onPostClick?.(post)} onHashtagClick=${onHashtagClick} />
            `)}
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
    const [connectionStatus, setConnectionStatus] = useState('disconnected');
    const [currentHashtag, setCurrentHashtag] = useState(null);
    const [notificationsEnabled, setNotificationsEnabled] = useState(Notification.permission === 'granted');
    
    // Refresh timestamps every 30 seconds
    useTimestampRefresh(30000);
    
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
            } else {
                const result = await getTimeline();
                setPosts(result.posts);
            }
        } catch (error) {
            console.error('Failed to load posts:', error);
        }
    }, []);
    
    // Handle hashtag click
    const handleHashtagClick = useCallback((hashtag) => {
        setCurrentHashtag(hashtag);
        setPosts(null); // Show loading
        loadPosts(hashtag);
    }, [loadPosts]);
    
    // Go back to timeline
    const handleBackToTimeline = useCallback(() => {
        setCurrentHashtag(null);
        setPosts(null);
        loadPosts();
    }, [loadPosts]);
    
    // Set up SSE connection
    useEffect(() => {
        loadPosts();
        
        const sse = new SSEClient(
            (eventType, data) => {
                // Add new posts/replies to timeline (only when on main timeline)
                if (!currentHashtag && (eventType === 'new_post' || eventType === 'agent_response')) {
                    setPosts(prev => prev ? [data, ...prev] : [data]);
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
    }, [loadPosts, currentHashtag, notificationsEnabled]);
    
    return html`
        <div class="container">
            <header class="header">
                ${currentHashtag ? html`
                    <button class="back-btn" onClick=${handleBackToTimeline}>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                    </button>
                    <h1>#${currentHashtag}</h1>
                ` : html`
                    <h1>Vibes</h1>
                `}
                <div class="header-actions">
                    <button 
                        class="notification-toggle ${notificationsEnabled ? 'enabled' : ''}" 
                        onClick=${enableNotifications}
                        title=${notificationsEnabled ? 'Notifications enabled' : 'Enable notifications'}
                    >
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
                            <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
                            ${!notificationsEnabled && html`<line x1="1" y1="1" x2="23" y2="23"/>`}
                        </svg>
                    </button>
                    <${ThemeToggle} />
                </div>
            </header>
            ${!currentHashtag && html`<${ComposeBox} onPost=${() => loadPosts()} />`}
            <${Timeline} 
                posts=${posts} 
                onHashtagClick=${handleHashtagClick}
                emptyMessage=${currentHashtag ? `No posts with #${currentHashtag}` : undefined}
            />
            <${ConnectionStatus} status=${connectionStatus} />
        </div>
    `;
}

// Mount the app
render(html`<${App} />`, document.getElementById('app'));
