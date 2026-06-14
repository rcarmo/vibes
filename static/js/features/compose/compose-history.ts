export const COMPOSE_HISTORY_MAX = 200;

export function normaliseComposeHistory(items: unknown[] | null | undefined): string[] {
    const seen = new Set<string>();
    const cleaned: string[] = [];
    for (const item of items || []) {
        if (typeof item !== 'string') continue;
        const trimmed = item.trim();
        if (!trimmed || seen.has(trimmed)) continue;
        seen.add(trimmed);
        cleaned.push(trimmed);
    }
    return cleaned;
}

export function loadComposeHistory(storageKey = 'vibes_compose_history'): string[] {
    if (typeof window === 'undefined') return [];
    try {
        const raw = localStorage.getItem(storageKey);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [];
        return normaliseComposeHistory(parsed);
    } catch {
        return [];
    }
}

export function saveComposeHistory(history: string[], storageKey = 'vibes_compose_history'): void {
    if (typeof window === 'undefined') return;
    try {
        localStorage.setItem(storageKey, JSON.stringify(history));
    } catch {
        // Ignore quota/security errors; compose history is opportunistic.
    }
}
