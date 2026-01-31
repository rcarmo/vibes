/**
 * API client for Vibes backend
 */

const API_BASE = '';

/**
 * Fetch wrapper with error handling
 */
async function request(url, options = {}) {
    const response = await fetch(API_BASE + url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(error.error || `HTTP ${response.status}`);
    }
    
    return response.json();
}

/**
 * Get timeline posts (chat style - returns oldest first)
 */
export async function getTimeline(limit = 10, beforeId = null) {
    let url = `/timeline?limit=${limit}`;
    if (beforeId) {
        url += `&before=${beforeId}`;
    }
    return request(url);
}

/**
 * Get posts by hashtag
 */
export async function getPostsByHashtag(hashtag, limit = 50, offset = 0) {
    return request(`/hashtag/${encodeURIComponent(hashtag)}?limit=${limit}&offset=${offset}`);
}

/**
 * Search posts
 */
export async function searchPosts(query, limit = 50, offset = 0) {
    return request(`/search?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`);
}

/**
 * Get a thread by ID
 */
export async function getThread(threadId) {
    return request(`/thread/${threadId}`);
}

/**
 * Create a new post
 */
export async function createPost(content, mediaIds = []) {
    return request('/post', {
        method: 'POST',
        body: JSON.stringify({ content, media_ids: mediaIds }),
    });
}

/**
 * Reply to a thread
 */
export async function createReply(threadId, content, mediaIds = []) {
    return request('/reply', {
        method: 'POST',
        body: JSON.stringify({ thread_id: threadId, content, media_ids: mediaIds }),
    });
}

/**
 * Send message to agent
 */
export async function sendAgentMessage(agentId, content, threadId = null, mediaIds = []) {
    return request(`/agent/${agentId}/message`, {
        method: 'POST',
        body: JSON.stringify({ content, thread_id: threadId, media_ids: mediaIds }),
    });
}

/**
 * Get available agents
 */
export async function getAgents() {
    return request('/agents');
}

/**
 * Upload media file
 */
export async function uploadMedia(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch(API_BASE + '/media/upload', {
        method: 'POST',
        body: formData,
    });
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Upload failed' }));
        throw new Error(error.error || `HTTP ${response.status}`);
    }
    
    return response.json();
}

/**
 * Respond to an agent request (permission, choice)
 */
export async function respondToAgentRequest(requestId, outcome) {
    const response = await fetch(API_BASE + '/agent/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId, outcome }),
    });
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Failed to respond' }));
        throw new Error(error.error || `HTTP ${response.status}`);
    }
    
    return response.json();
}

/**
 * Add pattern to permission whitelist
 */
export async function addToWhitelist(pattern, description) {
    const response = await fetch(API_BASE + '/agent/whitelist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pattern, description }),
    });
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ error: 'Failed to add to whitelist' }));
        throw new Error(error.error || `HTTP ${response.status}`);
    }
    
    return response.json();
}

/**
 * Get media URL
 */
export function getMediaUrl(mediaId) {
    return `${API_BASE}/media/${mediaId}`;
}

/**
 * Get media thumbnail URL
 */
export function getThumbnailUrl(mediaId) {
    return `${API_BASE}/media/${mediaId}/thumbnail`;
}

/**
 * Get media info (metadata without data)
 */
export async function getMediaInfo(mediaId) {
    const response = await fetch(`${API_BASE}/media/${mediaId}/info`);
    if (!response.ok) throw new Error('Failed to get media info');
    return response.json();
}

/**
 * SSE client for live updates
 */
export class SSEClient {
    constructor(onEvent, onStatusChange) {
        this.onEvent = onEvent;
        this.onStatusChange = onStatusChange;
        this.eventSource = null;
        this.reconnectTimeout = null;
        this.reconnectDelay = 1000;
    }
    
    connect() {
        if (this.eventSource) {
            this.eventSource.close();
        }
        
        this.eventSource = new EventSource(API_BASE + '/sse/stream');
        
        this.eventSource.onopen = () => {
            this.reconnectDelay = 1000;
            this.onStatusChange('connected');
        };
        
        this.eventSource.onerror = () => {
            this.onStatusChange('disconnected');
            this.scheduleReconnect();
        };
        
        // Event handlers
        this.eventSource.addEventListener('connected', () => {
            console.log('SSE connected');
        });
        
        this.eventSource.addEventListener('new_post', (e) => {
            this.onEvent('new_post', JSON.parse(e.data));
        });
        
        this.eventSource.addEventListener('new_reply', (e) => {
            this.onEvent('new_reply', JSON.parse(e.data));
        });
        
        this.eventSource.addEventListener('agent_response', (e) => {
            this.onEvent('agent_response', JSON.parse(e.data));
        });
        
        this.eventSource.addEventListener('interaction_updated', (e) => {
            this.onEvent('interaction_updated', JSON.parse(e.data));
        });
        
        this.eventSource.addEventListener('agent_status', (e) => {
            this.onEvent('agent_status', JSON.parse(e.data));
        });
        
        this.eventSource.addEventListener('agent_request', (e) => {
            this.onEvent('agent_request', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('agent_request_timeout', (e) => {
            this.onEvent('agent_request_timeout', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('agent_draft', (e) => {
            this.onEvent('agent_draft', JSON.parse(e.data));
        });
    }
    
    scheduleReconnect() {
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
        }
        
        this.reconnectTimeout = setTimeout(() => {
            console.log('Reconnecting SSE...');
            this.connect();
        }, this.reconnectDelay);
        
        // Exponential backoff, max 30 seconds
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
    }
    
    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
            this.reconnectTimeout = null;
        }
    }
}
