export function normalizeProviders(payload) {
    return Array.isArray(payload?.providers) ? payload.providers.filter(Boolean) : [];
}

export function resolveActiveProviderId(payload, previousId = null) {
    const providers = normalizeProviders(payload);
    if (previousId && providers.some((provider) => provider.id === previousId)) return previousId;
    return payload?.active
        || providers.find((provider) => provider.active)?.id
        || providers.find((provider) => provider.available)?.id
        || providers[0]?.id
        || null;
}

export function getProviderById(providers, providerId) {
    return (providers || []).find((provider) => provider?.id === providerId) || null;
}

export function getAvailableProviders(providers) {
    return (providers || []).filter((provider) => provider?.available);
}

export function canSwitchModels(provider) {
    const caps = provider?.capabilities || {};
    return Boolean(caps.model_list || caps.model_switch);
}

export function canSetThinking(provider) {
    const caps = provider?.capabilities || {};
    return Array.isArray(caps.thinking_levels) && caps.thinking_levels.length > 0;
}

export function providerCapabilitySummary(provider) {
    const caps = provider?.capabilities || {};
    const summary = [];
    if (caps.model_list || caps.model_switch) summary.push('models');
    if (Array.isArray(caps.thinking_levels) && caps.thinking_levels.length > 0) summary.push('thinking');
    if (caps.tool_events) summary.push('tools');
    if (caps.steering) summary.push('steering');
    if (caps.follow_up_queue) summary.push('queue');
    if (caps.session_stats || caps.session_compact) summary.push('sessions');
    return summary;
}

export function describeProvider(provider) {
    if (!provider) return 'No backend selected';
    const state = provider.available
        ? (provider.ready ? 'ready' : (provider.status || 'available'))
        : (provider.status || 'unavailable');
    const detail = providerCapabilitySummary(provider);
    const capabilities = detail.length ? ` · ${detail.join(' · ')}` : '';
    const error = provider.error ? ` — ${provider.error}` : '';
    return `${provider.label || provider.id} (${provider.transport || provider.family || 'backend'}): ${state}${capabilities}${error}`;
}

export function selectableBackendId(provider, fallbackId = null) {
    return provider?.available ? provider.id : fallbackId;
}
