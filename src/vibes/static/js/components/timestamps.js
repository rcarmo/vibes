// SQLite CURRENT_TIMESTAMP omits its UTC zone. Only normalise that known
// database shape; explicit ISO offsets must keep their original meaning.
export function parseTimestamp(value) {
    if (typeof value !== 'string' || !value.trim()) return null;
    const input = value.trim();
    const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(input)
        ? input.replace(' ', 'T') + 'Z' : input;
    const date = new Date(normalized);
    return Number.isFinite(date.getTime()) ? date : null;
}

export function formatRelativeTime(timestamp, now = Date.now()) {
    const date = parseTimestamp(timestamp);
    if (!date) return typeof timestamp === 'string' ? timestamp : '';
    const diffMs = Math.max(0, Number(now) - date.getTime());
    const diffSec = diffMs / 1000;
    const dayMs = 24 * 60 * 60 * 1000;
    if (diffMs < dayMs) {
        if (diffSec < 60) return 'just now';
        if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m`;
        return `${Math.floor(diffSec / 3600)}h`;
    }
    const time = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    if (diffMs < 5 * dayMs) return `${date.toLocaleDateString(undefined, { weekday: 'short' })} ${time}`;
    return `${date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${time}`;
}
