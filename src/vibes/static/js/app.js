import { html, render, useState, useEffect, useCallback } from './vendor/preact-htm.js';
import { getTimeline, createPost, sendAgentMessage, uploadMedia, getThumbnailUrl, SSEClient } from './api.js';

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
    return date.toLocaleDateString();
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
            ${dark ? '☀️' : '🌙'}
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
            await sendAgentMessage('default', content, null);
            
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
                    <label class="icon-btn">
                        📷
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
 * Single post component
 */
function Post({ post, onClick }) {
    const data = post.data;
    const isAgent = data.type === 'agent_response';
    
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
            <div class="post-content ${isAgent ? 'agent' : ''}">
                ${data.content}
            </div>
            ${data.media_ids?.length > 0 && html`
                <div class="media-preview">
                    ${data.media_ids.map(id => html`
                        <img key=${id} src=${getThumbnailUrl(id)} alt="Media" loading="lazy" />
                    `)}
                </div>
            `}
        </div>
    `;
}

/**
 * Timeline component
 */
function Timeline({ posts, onPostClick }) {
    if (!posts) {
        return html`<div class="loading"><div class="spinner"></div></div>`;
    }
    
    if (posts.length === 0) {
        return html`
            <div style="padding: var(--spacing-xl); text-align: center; color: var(--text-secondary)">
                No posts yet. Start a conversation!
            </div>
        `;
    }
    
    return html`
        <div class="timeline">
            ${posts.map(post => html`
                <${Post} key=${post.id} post=${post} onClick=${() => onPostClick?.(post)} />
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
    
    // Load initial timeline
    const loadTimeline = useCallback(async () => {
        try {
            const result = await getTimeline();
            setPosts(result.posts);
        } catch (error) {
            console.error('Failed to load timeline:', error);
        }
    }, []);
    
    // Set up SSE connection
    useEffect(() => {
        loadTimeline();
        
        const sse = new SSEClient(
            (eventType, data) => {
                // Add new posts/replies to timeline
                if (eventType === 'new_post' || eventType === 'agent_response') {
                    setPosts(prev => prev ? [data, ...prev] : [data]);
                }
            },
            setConnectionStatus
        );
        
        sse.connect();
        
        return () => sse.disconnect();
    }, [loadTimeline]);
    
    return html`
        <div class="container">
            <header class="header">
                <h1>Vibes</h1>
                <${ThemeToggle} />
            </header>
            <${ComposeBox} onPost=${loadTimeline} />
            <${Timeline} posts=${posts} />
            <${ConnectionStatus} status=${connectionStatus} />
        </div>
    `;
}

// Mount the app
render(html`<${App} />`, document.getElementById('app'));
