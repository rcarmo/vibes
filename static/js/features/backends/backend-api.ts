import { request } from '../../api.ts';
import type { ProviderPayload } from './provider-utils.ts';

export interface ThreadBackendPayload {
    thread_id?: string;
    backend_id?: string | null;
    provider?: string | null;
    transport?: string | null;
    status?: string;
    error?: string;
}

export interface SetThreadBackendPayload extends ThreadBackendPayload {
    previous_backend_id?: string | null;
}

/**
 * Get configured/detected backend providers and capabilities.
 */
export async function getAgentProviders(): Promise<ProviderPayload> {
    return request('/agent/providers') as Promise<ProviderPayload>;
}

/**
 * Get backend affinity for a thread.
 */
export async function getThreadBackend(threadId: string | number): Promise<ThreadBackendPayload> {
    return request(`/thread/${encodeURIComponent(String(threadId))}/backend`) as Promise<ThreadBackendPayload>;
}

/**
 * Switch backend affinity for a thread.
 */
export async function setThreadBackend(threadId: string | number, backendId: string): Promise<SetThreadBackendPayload> {
    return request(`/thread/${encodeURIComponent(String(threadId))}/backend`, {
        method: 'POST',
        body: JSON.stringify({ backend_id: backendId }),
    }) as Promise<SetThreadBackendPayload>;
}
