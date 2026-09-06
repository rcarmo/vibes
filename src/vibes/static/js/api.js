/**
 * API client for Vibes backend
 */

const API_BASE = '';

/**
 * Fetch wrapper with error handling
 */
async function request(url, options = {}, includeEtag = false) {
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
    
    const data = await response.json();
    return includeEtag ? { ...data, etag: response.headers.get('ETag') } : data;
}

/**
 * Get timeline posts (chat style - returns oldest first)
 */
export async function getTimeline(limit = 10, beforeId = null, sessionId = 'default') {
    let url = `/timeline?limit=${limit}&session_id=${encodeURIComponent(sessionId)}`;
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
export async function searchPosts(query, limit = 50, offset = 0, filters = {}) {
    const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
    if (filters.images) params.set('has_images', 'true');
    if (filters.attachments) params.set('has_attachments', 'true');
    if (filters.threadId) params.set('thread_id', String(filters.threadId));
    if (filters.sessionId) params.set('session_id', filters.sessionId);
    if (filters.scope === 'root') params.set('scope', 'root');
    return request(`/search?${params}`);
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
 * Delete a post (optionally cascade replies)
 */
export async function deletePost(postId, cascade = false) {
    const url = `/post/${postId}?cascade=${cascade ? 'true' : 'false'}`;
    return request(url, { method: 'DELETE' });
}

/**
 * Send message to agent
 */
export async function sendAgentMessage(agentId, content, threadId = null, mediaIds = [], mode = null, sessionId = 'default') {
    return request(`/agent/${agentId}/message`, {
        method: 'POST',
        body: JSON.stringify({ content, thread_id: threadId, media_ids: mediaIds, mode, session_id: sessionId }),
    });
}

/**
 * Get available agents
 */
export async function getSessionModels(sessionId) {
    return request(`/sessions/${encodeURIComponent(sessionId)}/models`);
}

export async function changeSessionModel(sessionId, changes) {
    return request(`/sessions/${encodeURIComponent(sessionId)}/model`, { method: 'POST', body: JSON.stringify(changes) });
}

export async function getSessionModelState(sessionId) {
    return request(`/sessions/${encodeURIComponent(sessionId)}/model-state`);
}

export async function getSessions(includeArchived = false) {
    return request(`/sessions?include_archived=${includeArchived}`);
}

export async function getSessionTimeline(sessionId, limit = 10, beforeId = null) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (beforeId) params.set('before', String(beforeId));
    return request(`/sessions/${encodeURIComponent(sessionId)}/timeline?${params}`);
}

export async function createSession(name, parentId = null) {
    return request('/sessions', { method: 'POST', body: JSON.stringify({ name, parent_id: parentId }) });
}

export async function updateSession(sessionId, changes) {
    return request(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'PATCH', body: JSON.stringify(changes) });
}

export async function deleteSession(sessionId) {
    return request(`/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
}

export async function getAgents() {
    return request('/agents');
}

/**
 * Get context window usage (tokens, contextWindow, percent).
 */
export async function getAgentContext(sessionId = 'default') {
    return request(`/agent/context?session_id=${encodeURIComponent(sessionId)}`);
}

/**
 * Get current agent busy state and active turns (for polling on SSE reconnect).
 */
export async function getAgentStatus(sessionId = 'default') {
    return request(`/agents/status?session_id=${encodeURIComponent(sessionId)}`);
}

export async function getAgentQueue(agentId = null, threadId = null, sessionId = null) {
    const params = new URLSearchParams();
    if (agentId) params.set('agent_id', agentId);
    if (threadId != null) params.set('thread_id', String(threadId));
    if (sessionId !== null) params.set('session_id', sessionId);
    const query = params.toString();
    return request(query ? `/agent/queue?${query}` : '/agent/queue');
}

export async function removeAgentQueueItem(rowId) {
    return request('/agent/queue-remove', {
        method: 'POST',
        body: JSON.stringify({ row_id: rowId }),
    });
}

export async function reorderAgentQueueItem(rowId, direction) {
    return request('/agent/queue-reorder', { method: 'POST', body: JSON.stringify({ row_id: rowId, direction }) });
}

export async function steerAgentQueueItem(rowId) {
    return request('/agent/queue-steer', {
        method: 'POST',
        body: JSON.stringify({ row_id: rowId }),
    });
}

/**
 * Get available models and current selection.
 */
export async function getAgentModels() {
    return request('/agent/models');
}

/**
 * Get full draft/thought text for a live agent turn.
 */
export async function getAgentTurnPreview(turnId) {
    return request(`/agent/turn/${encodeURIComponent(turnId)}`);
}

/**
 * Set expanded state for a live draft/thought panel.
 */
export async function setAgentTurnPanelExpanded(turnId, panel, expanded) {
    return request(`/agent/turn/${encodeURIComponent(turnId)}/panel`, {
        method: 'POST',
        body: JSON.stringify({ panel, expanded: Boolean(expanded) }),
    });
}

/**
 * Upload media file
 */
export async function uploadMedia(file, { signal, onProgress } = {}) {
    if (signal || onProgress) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const abort = () => xhr.abort();
            const finish = (error, value) => {
                signal?.removeEventListener('abort', abort);
                if (error) reject(error); else resolve(value);
            };
            if (signal?.aborted) { reject(new DOMException('Upload cancelled', 'AbortError')); return; }
            xhr.open('POST', API_BASE + '/media/upload');
            xhr.upload.onprogress = e => {
                if (e.lengthComputable) onProgress?.(Math.round(e.loaded / e.total * 100));
            };
            xhr.onload = () => {
                let value;
                try { value = JSON.parse(xhr.responseText); }
                catch { finish(new Error('Invalid upload response')); return; }
                finish(xhr.status >= 200 && xhr.status < 300 ? null : new Error(value.error || `HTTP ${xhr.status}`), value);
            };
            xhr.onerror = () => finish(new Error('Upload network error'));
            xhr.onabort = () => finish(new DOMException('Upload cancelled', 'AbortError'));
            signal?.addEventListener('abort', abort, { once: true });
            const data = new FormData();
            data.append('file', file);
            xhr.send(data);
        });
    }
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
 * Get workspace tree.
 */
export async function getWorkspaceTree(path = '', depth = 2, showHidden = false) {
    return request(`/workspace/tree?path=${encodeURIComponent(path)}&depth=${depth}&show_hidden=${showHidden ? '1' : '0'}`);
}

/**
 * Get workspace file preview.
 */
export async function getWorkspaceFile(path, maxBytes = 20_000, mode = null) {
    const modeParam = mode ? `&mode=${encodeURIComponent(mode)}` : '';
    return request(`/workspace/file?path=${encodeURIComponent(path)}&max=${maxBytes}${modeParam}`);
}

/**
 * Update workspace file contents.
 */
export async function updateWorkspaceFile(path, content) {
    return request('/workspace/file', {
        method: 'PUT',
        body: JSON.stringify({ path, content }),
    });
}

/**
 * Upload a file to the workspace via multipart form data.
 */
export async function uploadWorkspaceFile(file, targetPath = '', options = {}) {
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams();
    if (targetPath) params.set('path', targetPath);
    if (options.overwrite) params.set('overwrite', '1');
    const query = params.toString();
    const url = query ? `/workspace/upload?${query}` : '/workspace/upload';
    const response = await fetch(API_BASE + url, {
        method: 'POST',
        body: formData,
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({ error: 'Upload failed' }));
        const err = new Error(body.error || `HTTP ${response.status}`);
        err.status = response.status;
        err.code = body.code;
        throw err;
    }
    return response.json();
}

/**
 * Attach workspace file to conversation as media.
 */
export async function attachWorkspaceFile(path) {
    return request('/workspace/attach', {
        method: 'POST',
        body: JSON.stringify({ path }),
    });
}

/**
 * Delete a file from the workspace.
 */
export async function deleteWorkspaceFile(path) {
    const url = `/workspace/file?path=${encodeURIComponent(path || '')}`;
    return request(url, { method: 'DELETE' });
}

/**
 * Create a new workspace file.
 */
export async function createWorkspaceFile(path, name, content = '') {
    return request('/workspace/create', {
        method: 'POST',
        body: JSON.stringify({ path, name, content }),
    });
}

/**
 * Rename a workspace file or folder.
 */
export async function renameWorkspaceFile(path, name) {
    return request('/workspace/rename', {
        method: 'POST',
        body: JSON.stringify({ path, name }),
    });
}

/**
 * Move a workspace file or folder into another directory.
 */
export async function moveWorkspaceEntry(path, target) {
    return request('/workspace/move', {
        method: 'POST',
        body: JSON.stringify({ path, target }),
    });
}

/**
 * Toggle workspace visibility state.
 */
export async function setWorkspaceVisibility(visible, showHidden = false) {
    return request('/workspace/visibility', {
        method: 'POST',
        body: JSON.stringify({ visible: Boolean(visible), show_hidden: Boolean(showHidden) }),
    });
}

/**
 * Get raw workspace file URL.
 */
export function getWorkspaceRawUrl(path) {
    return `${API_BASE}/workspace/raw?path=${encodeURIComponent(path)}`;
}

/**
 * Get workspace folder download URL (zip)
 */
export function getWorkspaceDownloadUrl(path, showHidden = false) {
    const query = `path=${encodeURIComponent(path || '')}&show_hidden=${showHidden ? '1' : '0'}`;
    return `${API_BASE}/workspace/download?${query}`;
}

export async function getAgentCommands() {
    return request('/agent/commands');
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
        this.status = 'disconnected';
        this.reconnectAttempts = 0;
        this.cooldownUntil = 0;
        this.connecting = false;
    }
    
    connect() {
        if (this.connecting) return;
        if (this.eventSource && this.status === 'connected') return;
        this.connecting = true;
        if (this.eventSource) {
            this.eventSource.close();
        }
        
        this.eventSource = new EventSource(API_BASE + '/sse/stream');
        
        this.eventSource.onopen = () => {
            this.connecting = false;
            this.reconnectDelay = 1000;
            this.reconnectAttempts = 0;
            this.cooldownUntil = 0;
            this.status = 'connected';
            this.onStatusChange('connected');
        };
        
        this.eventSource.onerror = () => {
            this.connecting = false;
            this.status = 'disconnected';
            this.onStatusChange('disconnected');
            this.reconnectAttempts += 1;
            this.scheduleReconnect();
        };
        
        // Event handlers
        this.eventSource.addEventListener('connected', () => {
            console.log('SSE connected');
            this.onEvent('connected', {});
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

        this.eventSource.addEventListener('interaction_deleted', (e) => {
            this.onEvent('interaction_deleted', JSON.parse(e.data));
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

        this.eventSource.addEventListener('agent_thought', (e) => {
            this.onEvent('agent_thought', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('agent_draft_delta', (e) => {
            this.onEvent('agent_draft_delta', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('agent_thought_delta', (e) => {
            this.onEvent('agent_thought_delta', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('agent_steer_queued', (e) => {
            this.onEvent('agent_steer_queued', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('agent_followup_queued', (e) => {
            this.onEvent('agent_followup_queued', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('agent_followup_consumed', (e) => {
            this.onEvent('agent_followup_consumed', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('agent_followup_removed', (e) => {
            this.onEvent('agent_followup_removed', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('model_changed', (e) => {
            this.onEvent('model_changed', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('agents_changed', (e) => {
            this.onEvent('agents_changed', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('workspace_update', (e) => {
            this.onEvent('workspace_update', JSON.parse(e.data));
        });

        this.eventSource.addEventListener('ui_theme', (e) => {
            this.onEvent('ui_theme', JSON.parse(e.data));
        });
    }
    
    scheduleReconnect() {
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
        }

        const MAX_ATTEMPTS = 10;
        const COOLDOWN_MS = 60_000;
        const now = Date.now();
        if (this.reconnectAttempts >= MAX_ATTEMPTS) {
            this.cooldownUntil = Math.max(this.cooldownUntil, now + COOLDOWN_MS);
            this.reconnectAttempts = 0;
        }
        const cooldownDelay = Math.max(this.cooldownUntil - now, 0);
        const delay = Math.max(this.reconnectDelay, cooldownDelay);
        
        this.reconnectTimeout = setTimeout(() => {
            console.log('Reconnecting SSE...');
            this.connect();
        }, delay);
        
        // Exponential backoff, max 30 seconds
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
    }

    reconnectIfNeeded() {
        if (this.status === 'connected') return;
        const now = Date.now();
        if (this.cooldownUntil && now < this.cooldownUntil) return;
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
            this.reconnectTimeout = null;
        }
        this.connect();
    }
    
    disconnect() {
        this.connecting = false;
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

export async function getModelPreferences() {
    return request('/model-preferences', {}, true);
}

export async function saveModelPreferences(pins, etag) {
    if (!etag) throw new Error('Load instance preferences before saving');
    return request('/model-preferences', { method: 'PUT', headers: { 'If-Match': etag }, body: JSON.stringify({ pins }) }, true);
}
