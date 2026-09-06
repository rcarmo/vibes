export function sessionMessageCount(value) {
    return Number.isSafeInteger(value) && value >= 0
        ? `${value} ${value === 1 ? 'message' : 'messages'}`
        : 'Message count unavailable';
}

// Persisted message timestamps describe history, not live agent availability.
export function sessionLastMessage(value) {
    if (typeof value !== 'string' || !value.trim()) return null;
    // SQLite CURRENT_TIMESTAMP is UTC despite omitting an explicit zone.
    const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
        ? value.replace(' ', 'T') + 'Z' : value;
    const date = new Date(normalized);
    if (!Number.isFinite(date.getTime())) return null;
    return { datetime: date.toISOString(), label: date.toLocaleString() };
}
