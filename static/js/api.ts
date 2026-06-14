/**
 * API client for Vibes backend.
 */

const API_BASE = '';

type JsonRecord = Record<string, unknown>;
type RequestOptions = RequestInit & { headers?: HeadersInit };

export interface ApiError extends Error {
    status?: number;
    code?: unknown;
}

function errorMessage(payload: unknown, fallback: string): string {
    if (payload && typeof payload === 'object' && typeof (payload as { error?: unknown }).error === 'string') {
        return (payload as { error: string }).error;
    }
    return fallback;
}

async function readJsonError(response: Response, fallback: string): Promise<any> {
    return response.json().catch(() => ({ error: fallback }));
}

/**
 * Fetch wrapper with error handling.
 */
export async function request<T = any>(url: string, options: RequestOptions = {}): Promise<T> {
    const response = await fetch(API_BASE + url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });

    if (!response.ok) {
        const error = await readJsonError(response, 'Unknown error');
        throw new Error(errorMessage(error, `HTTP ${response.status}`));
    }

    if (response.status === 204) return {} as T;
    const text = await response.text();
    return (text ? JSON.parse(text) : {}) as T;
}

/**
 * Get timeline posts (chat style - returns oldest first).
 */
export async function getTimeline(limit = 10, beforeId: string | number | null = null): Promise<any> {
    let url = `/timeline?limit=${limit}`;
    if (beforeId) {
        url += `&before_id=${beforeId}`;
    }
    return request(url);
}

/**
 * Get posts by hashtag.
 */
export async function getPostsByHashtag(hashtag: string, limit = 50, offset = 0): Promise<any> {
    return request(`/hashtag/${encodeURIComponent(hashtag)}?limit=${limit}&offset=${offset}`);
}

/**
 * Search posts.
 */
export async function searchPosts(query: string, limit = 50, offset = 0): Promise<any> {
    return request(`/search?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`);
}

/**
 * Get a thread by ID.
 */
export async function getThread(threadId: string | number): Promise<any> {
    return request(`/thread/${threadId}`);
}

/**
 * Create a new post.
 */
export async function createPost(content: string, mediaIds: unknown[] = []): Promise<any> {
    return request('/post', {
        method: 'POST',
        body: JSON.stringify({ content, media_ids: mediaIds }),
    });
}

/**
 * Reply to a thread.
 */
export async function createReply(threadId: string | number, content: string, mediaIds: unknown[] = []): Promise<any> {
    return request('/thread', {
        method: 'POST',
        body: JSON.stringify({ thread_id: threadId, content, media_ids: mediaIds }),
    });
}

/**
 * Delete a post (optionally cascade replies).
 */
export async function deletePost(postId: string | number, cascade = false): Promise<any> {
    const url = `/post/${postId}?cascade=${cascade ? 'true' : 'false'}`;
    return request(url, { method: 'DELETE' });
}

/**
 * Send message to agent.
 */
export async function sendAgentMessage(
    agentId: string,
    content: string,
    threadId: string | number | null = null,
    mediaIds: unknown[] = [],
    mode: string | null = null,
    backendId: string | null = null,
): Promise<any> {
    return request(`/agent/${agentId}/message`, {
        method: 'POST',
        body: JSON.stringify({ content, thread_id: threadId, media_ids: mediaIds, mode, backend_id: backendId }),
    });
}

/**
 * Get available agents.
 */
export async function getAgents(): Promise<any> {
    const data = await request<unknown>('/agents');
    return Array.isArray(data) ? { agents: data } : data;
}

/**
 * Get context window usage (tokens, contextWindow, percent).
 */
export async function getAgentContext(): Promise<any> {
    return request('/agent/context');
}

/**
 * Get current agent busy state and active turns (for polling on SSE reconnect).
 */
export async function getAgentStatus(): Promise<any> {
    return request('/agent/status');
}

export async function getAgentQueue(agentId: string | null = null, threadId: string | number | null = null): Promise<any> {
    const params = new URLSearchParams();
    if (agentId) params.set('agent_id', agentId);
    if (threadId != null) params.set('thread_id', String(threadId));
    const query = params.toString();
    return request(query ? `/agent/queue?${query}` : '/agent/queue');
}

export async function removeAgentQueueItem(rowId: string | number): Promise<any> {
    return request('/agent/queue-remove', {
        method: 'POST',
        body: JSON.stringify({ row_id: rowId }),
    });
}

export async function steerAgentQueueItem(rowId: string | number): Promise<any> {
    return request('/agent/queue-steer', {
        method: 'POST',
        body: JSON.stringify({ row_id: rowId }),
    });
}

/**
 * Get available models and current selection.
 */
export async function getAgentModels(): Promise<any> {
    return request('/agent/models');
}

/**
 * Get full draft/thought text for a live agent turn.
 */
export async function getAgentTurnPreview(turnId: string | number): Promise<any> {
    return request(`/agent/turn/${encodeURIComponent(String(turnId))}`);
}

/**
 * Set expanded state for a live draft/thought panel.
 */
export async function setAgentTurnPanelExpanded(turnId: string | number, panel: string, expanded: boolean): Promise<any> {
    return request(`/agent/turn/${encodeURIComponent(String(turnId))}/panel`, {
        method: 'POST',
        body: JSON.stringify({ panel, expanded: Boolean(expanded) }),
    });
}

/**
 * Upload media file.
 */
export async function uploadMedia(file: Blob): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(API_BASE + '/media/upload', {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const error = await readJsonError(response, 'Upload failed');
        throw new Error(errorMessage(error, `HTTP ${response.status}`));
    }

    return response.json();
}

/**
 * Respond to an agent request (permission, choice).
 */
export async function respondToAgentRequest(requestId: string, outcome: string): Promise<any> {
    const response = await fetch(API_BASE + '/agent/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId, outcome }),
    });

    if (!response.ok) {
        const error = await readJsonError(response, 'Failed to respond');
        throw new Error(errorMessage(error, `HTTP ${response.status}`));
    }

    return response.json();
}

/**
 * Add pattern to permission whitelist.
 */
export async function addToWhitelist(pattern: string, description: string): Promise<any> {
    const response = await fetch(API_BASE + '/agent/whitelist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pattern, description }),
    });

    if (!response.ok) {
        const error = await readJsonError(response, 'Failed to add to whitelist');
        throw new Error(errorMessage(error, `HTTP ${response.status}`));
    }

    return response.json();
}

/**
 * Get media URL.
 */
export function getMediaUrl(mediaId: string | number): string {
    return `${API_BASE}/media/${mediaId}`;
}

/**
 * Get media thumbnail URL.
 */
export function getThumbnailUrl(mediaId: string | number): string {
    return `${API_BASE}/media/${mediaId}/thumbnail`;
}

/**
 * Get media info (metadata without data).
 */
export async function getMediaInfo(mediaId: string | number): Promise<any> {
    const response = await fetch(`${API_BASE}/media/${mediaId}/info`);
    if (!response.ok) throw new Error('Failed to get media info');
    return response.json();
}

/**
 * Get workspace tree.
 */
export async function getWorkspaceTree(path = '', depth = 2, showHidden = false): Promise<any> {
    return request(`/workspace/tree?path=${encodeURIComponent(path)}&depth=${depth}&show_hidden=${showHidden ? 'true' : 'false'}`);
}

/**
 * Get workspace file preview.
 */
export async function getWorkspaceFile(path: string, maxBytes = 20_000, mode: string | null = null): Promise<any> {
    const modeParam = mode ? `&mode=${encodeURIComponent(mode)}` : '';
    return request(`/workspace/file?path=${encodeURIComponent(path)}&max_bytes=${maxBytes}${modeParam}`);
}

/**
 * Update workspace file contents.
 */
export async function updateWorkspaceFile(path: string, content: string, mtime: string | null = null): Promise<any> {
    const body: JsonRecord = { path, content };
    if (mtime) body.mtime = mtime;
    return request('/workspace/file', {
        method: 'PUT',
        body: JSON.stringify(body),
    });
}

export interface UploadWorkspaceOptions {
    overwrite?: boolean;
}

/**
 * Upload a file to the workspace via multipart form data.
 */
export async function uploadWorkspaceFile(file: Blob, targetPath = '', options: UploadWorkspaceOptions = {}): Promise<any> {
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
        const body = await readJsonError(response, 'Upload failed') as { error?: string; code?: unknown };
        const err = new Error(body.error || `HTTP ${response.status}`) as ApiError;
        err.status = response.status;
        err.code = body.code;
        throw err;
    }
    return response.json();
}

/**
 * Delete a file from the workspace.
 */
export async function deleteWorkspaceFile(path: string): Promise<any> {
    const url = `/workspace/file?path=${encodeURIComponent(path || '')}`;
    return request(url, { method: 'DELETE' });
}

/**
 * Create a new workspace file.
 */
export async function createWorkspaceFile(path: string, name: string, content = ''): Promise<any> {
    return request('/workspace/create', {
        method: 'POST',
        body: JSON.stringify({ path, name, content }),
    });
}

/**
 * Rename a workspace file or folder.
 */
export async function renameWorkspaceFile(path: string, name: string): Promise<any> {
    const parts = String(path || '').split('/');
    parts.pop();
    const parent = parts.join('/');
    const nextPath = parent ? `${parent}/${name}` : name;
    return request('/workspace/rename', {
        method: 'POST',
        body: JSON.stringify({ from: path, to: nextPath }),
    });
}

/**
 * Move a workspace file or folder into another directory.
 */
export async function moveWorkspaceEntry(path: string, target: string): Promise<any> {
    return request('/workspace/move', {
        method: 'POST',
        body: JSON.stringify({ path, target }),
    });
}

/**
 * Toggle workspace visibility state.
 */
export async function setWorkspaceVisibility(visible: boolean, showHidden = false): Promise<any> {
    return request('/workspace/visibility', {
        method: 'POST',
        body: JSON.stringify({ visible: Boolean(visible), show_hidden: Boolean(showHidden) }),
    });
}

/**
 * Get raw workspace file URL.
 */
export function getWorkspaceRawUrl(path: string): string {
    return `${API_BASE}/workspace/raw?path=${encodeURIComponent(path)}`;
}

/**
 * Get workspace folder download URL (zip).
 */
export function getWorkspaceDownloadUrl(path: string, showHidden = false): string {
    const query = `path=${encodeURIComponent(path || '')}&show_hidden=${showHidden ? 'true' : 'false'}`;
    return `${API_BASE}/workspace/download?${query}`;
}

export async function getAgentCommands(): Promise<any> {
    return request('/agent/commands');
}

export type SSEStatus = 'connected' | 'disconnected';
export type SSEEventHandler = (type: string, payload: unknown) => void;
export type SSEStatusHandler = (status: SSEStatus) => void;

/**
 * SSE client for live updates.
 */
export class SSEClient {
    private onEvent: SSEEventHandler;
    private onStatusChange: SSEStatusHandler;
    private eventSource: EventSource | null = null;
    private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    private reconnectDelay = 1000;
    private status: SSEStatus = 'disconnected';
    private reconnectAttempts = 0;
    private cooldownUntil = 0;
    private connecting = false;

    constructor(onEvent: SSEEventHandler, onStatusChange: SSEStatusHandler) {
        this.onEvent = onEvent;
        this.onStatusChange = onStatusChange;
    }

    connect(): void {
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

        this.eventSource.addEventListener('connected', () => {
            console.log('SSE connected');
            this.onEvent('connected', {});
        });

        const jsonEvents = [
            'new_post',
            'new_reply',
            'agent_response',
            'interaction_updated',
            'interaction_deleted',
            'agent_status',
            'agent_request',
            'agent_request_timeout',
            'agent_draft',
            'agent_thought',
            'agent_draft_delta',
            'agent_thought_delta',
            'agent_steer_queued',
            'agent_followup_queued',
            'agent_followup_consumed',
            'agent_followup_removed',
            'model_changed',
            'agents_changed',
            'workspace_update',
            'ui_theme',
            'extension_event',
        ];
        for (const eventName of jsonEvents) {
            this.eventSource.addEventListener(eventName, (event) => {
                this.onEvent(eventName, JSON.parse((event as MessageEvent).data));
            });
        }
    }

    scheduleReconnect(): void {
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

        // Exponential backoff, max 30 seconds.
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
    }

    reconnectIfNeeded(): void {
        if (this.status === 'connected') return;
        const now = Date.now();
        if (this.cooldownUntil && now < this.cooldownUntil) return;
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
            this.reconnectTimeout = null;
        }
        this.connect();
    }

    disconnect(): void {
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
