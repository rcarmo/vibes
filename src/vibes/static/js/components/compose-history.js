// Chat-specific history. Only the default session may inherit legacy history.
export function historyKey(sessionId = 'default') {
    return `vibes_compose_history:${encodeURIComponent(sessionId)}`;
}

export function loadComposeHistory(storage, sessionId = 'default') {
    try {
        const raw = storage.getItem(historyKey(sessionId))
            ?? (sessionId === 'default' ? storage.getItem('vibes_compose_history') : null);
        const value = JSON.parse(raw || '[]');
        if (!Array.isArray(value)) return [];
        return [...new Set(value.filter(item => typeof item === 'string').map(item => item.trim()).filter(Boolean))].slice(-200);
    } catch { return []; }
}

export function saveComposeHistory(storage, sessionId, entries) {
    try { storage.setItem(historyKey(sessionId), JSON.stringify(entries.slice(-200))); }
    catch { /* Private browsing/storage quota must not break message submission. */ }
}
