export interface ProviderCapabilities {
    streaming_drafts?: boolean;
    streaming_thoughts?: boolean;
    tool_events?: boolean;
    permission_requests?: boolean;
    model_list?: boolean;
    model_switch?: boolean;
    thinking_levels?: string[];
    session_reset?: boolean;
    session_compact?: boolean;
    session_rename?: boolean;
    session_stats?: boolean;
    message_history?: boolean;
    commands_list?: boolean;
    steering?: boolean;
    follow_up_queue?: boolean;
    working_directory?: boolean;
    tools_mode?: string[];
    fs_read_text_file?: boolean;
    fs_write_text_file?: boolean;
    terminal_services?: boolean;
}

export interface ProviderDescriptor {
    id: string;
    label?: string;
    family?: string;
    transport?: string;
    command?: string;
    configured?: boolean;
    detected?: boolean;
    available?: boolean;
    ready?: boolean;
    active?: boolean;
    status?: string;
    error?: string;
    model?: string;
    capabilities?: ProviderCapabilities;
}

export interface ProviderPayload {
    providers?: ProviderDescriptor[];
    active?: string | null;
}

export function normalizeProviders(payload: ProviderPayload | null | undefined): ProviderDescriptor[] {
    return Array.isArray(payload?.providers) ? payload.providers.filter(Boolean) : [];
}

export function resolveActiveProviderId(payload: ProviderPayload | null | undefined, previousId: string | null = null): string | null {
    const providers = normalizeProviders(payload);
    if (previousId && providers.some((provider) => provider.id === previousId)) return previousId;
    return payload?.active
        || providers.find((provider) => provider.active)?.id
        || providers.find((provider) => provider.available)?.id
        || providers[0]?.id
        || null;
}

export function getProviderById(providers: ProviderDescriptor[] | null | undefined, providerId: string | null | undefined): ProviderDescriptor | null {
    return (providers || []).find((provider) => provider?.id === providerId) || null;
}

export function getAvailableProviders(providers: ProviderDescriptor[] | null | undefined): ProviderDescriptor[] {
    return (providers || []).filter((provider) => provider?.available);
}

export function canSwitchModels(provider: ProviderDescriptor | null | undefined): boolean {
    const caps = provider?.capabilities || {};
    return Boolean(caps.model_list || caps.model_switch);
}

export function canSetThinking(provider: ProviderDescriptor | null | undefined): boolean {
    const caps = provider?.capabilities || {};
    return Array.isArray(caps.thinking_levels) && caps.thinking_levels.length > 0;
}

export function canReadTextFiles(provider: ProviderDescriptor | null | undefined): boolean {
    return Boolean(provider?.capabilities?.fs_read_text_file);
}

export function canWriteTextFiles(provider: ProviderDescriptor | null | undefined): boolean {
    return Boolean(provider?.capabilities?.fs_write_text_file);
}

export function canUseTerminalServices(provider: ProviderDescriptor | null | undefined): boolean {
    return Boolean(provider?.capabilities?.terminal_services);
}

export function providerCapabilitySummary(provider: ProviderDescriptor | null | undefined): string[] {
    const caps = provider?.capabilities || {};
    const summary: string[] = [];
    if (caps.model_list || caps.model_switch) summary.push('models');
    if (Array.isArray(caps.thinking_levels) && caps.thinking_levels.length > 0) summary.push('thinking');
    if (caps.tool_events) summary.push('tools');
    if (caps.permission_requests) summary.push('permissions');
    if (caps.fs_read_text_file) summary.push('read-only fs');
    if (caps.fs_write_text_file) summary.push('write fs');
    if (caps.terminal_services) summary.push('terminal');
    if (caps.steering) summary.push('steering');
    if (caps.follow_up_queue) summary.push('queue');
    if (caps.session_stats || caps.session_compact) summary.push('sessions');
    return summary;
}

export function describeProvider(provider: ProviderDescriptor | null | undefined): string {
    if (!provider) return 'No backend selected';
    const state = provider.available
        ? (provider.ready ? 'ready' : (provider.status || 'available'))
        : (provider.status || 'unavailable');
    const detail = providerCapabilitySummary(provider);
    const capabilities = detail.length ? ` · ${detail.join(' · ')}` : '';
    const error = provider.error ? ` — ${provider.error}` : '';
    return `${provider.label || provider.id} (${provider.transport || provider.family || 'backend'}): ${state}${capabilities}${error}`;
}

export function selectableBackendId(provider: ProviderDescriptor | null | undefined, fallbackId: string | null = null): string | null {
    return provider?.available ? provider.id : fallbackId;
}
