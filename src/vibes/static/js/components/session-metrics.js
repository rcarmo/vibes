import { parseTimestamp } from './timestamps.js';

export function sessionMessageCount(value) {
    return Number.isSafeInteger(value) && value >= 0
        ? `${value} ${value === 1 ? 'message' : 'messages'}`
        : 'Message count unavailable';
}

// Persisted message timestamps describe history, not live agent availability.
export function sessionLastMessage(value) {
    if (typeof value !== 'string' || !value.trim()) return null;
    const date = parseTimestamp(value);
    if (!date) return null;
    return { datetime: date.toISOString(), label: date.toLocaleString() };
}
