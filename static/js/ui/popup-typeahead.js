/**
 * Popup typeahead — keyboard-driven item filtering for popup menus.
 *
 * Ported from piclaw's runtime/web/src/ui/popup-typeahead.ts.
 * Used in the model picker and slash command autocomplete.
 *
 * Behavior:
 * - Buffers printable keystrokes with a 700ms idle reset
 * - Matches items by prefix first, then substring
 * - Rotates from the current active index (wrap-around)
 * - Normalizes labels (lowercase, strip @, collapse whitespace)
 */

export const POPUP_TYPEAHEAD_RESET_MS = 700;

/**
 * Check if a keyboard event is a printable typeahead key.
 * Rejects modifier combos, IME composition, and non-printable keys.
 */
export function isPopupTypeaheadKey(event) {
    if (!event) return false;
    if (event.isComposing) return false;
    if (event.ctrlKey || event.metaKey || event.altKey) return false;
    return typeof event.key === 'string' && event.key.length === 1 && /\S/.test(event.key);
}

/**
 * Update the typeahead buffer with a new keystroke.
 * Resets if idle longer than resetMs.
 *
 * @param {Object|null} previous - Previous buffer state {value, updatedAt}
 * @param {string} key - The pressed key character
 * @param {number} now - Current timestamp (default: Date.now())
 * @param {number} resetMs - Idle timeout before reset (default: 700)
 * @returns {{ value: string, updatedAt: number }}
 */
export function updatePopupTypeaheadBuffer(previous, key, now = Date.now(), resetMs = POPUP_TYPEAHEAD_RESET_MS) {
    const prior = previous && typeof previous === 'object' ? previous : { value: '', updatedAt: 0 };
    const char = String(key || '').trim().toLowerCase();
    if (!char) return { value: '', updatedAt: now };
    const shouldReset = !prior.value || !Number.isFinite(prior.updatedAt) || (now - prior.updatedAt) > resetMs;
    return {
        value: shouldReset ? char : `${prior.value}${char}`,
        updatedAt: now,
    };
}

/**
 * Find the best matching item index, rotating from startIndex.
 * Prefers prefix matches over substring matches.
 *
 * @param {Array} items - The items to search
 * @param {string} query - The typeahead query string
 * @param {number} startIndex - Start searching from this index (wraps around)
 * @param {Function} getLabel - Extract label from item (default: identity)
 * @returns {number} Matching index, or -1 if no match
 */
export function findPopupTypeaheadMatch(items, query, startIndex = 0, getLabel = (item) => item) {
    const normalizedQuery = normalize(query);
    if (!normalizedQuery) return -1;
    const list = Array.isArray(items) ? items : [];
    const indices = rotatedIndices(list.length, startIndex);
    const labels = list.map((item) => normalize(getLabel(item)));

    // Prefix matches first
    for (const idx of indices) {
        if (labels[idx].startsWith(normalizedQuery)) return idx;
    }
    // Then substring matches
    for (const idx of indices) {
        if (labels[idx].includes(normalizedQuery)) return idx;
    }
    return -1;
}

/**
 * Resolve a typeahead match, keeping the current item if it still matches.
 * Prevents the cursor from jumping away when refining a query (e.g., "c" → "co" → "codex").
 *
 * @param {Array} items - The items to search
 * @param {string} query - The typeahead query string
 * @param {number} currentIndex - Currently highlighted index
 * @param {Function} getLabel - Extract label from item
 * @returns {number} Best matching index
 */
export function resolvePopupTypeaheadMatch(items, query, currentIndex = -1, getLabel = (item) => item) {
    const list = Array.isArray(items) ? items : [];
    if (currentIndex >= 0 && currentIndex < list.length) {
        const currentLabel = getLabel(list[currentIndex]);
        if (labelMatchesQuery(currentLabel, query)) {
            return currentIndex;
        }
    }
    return findPopupTypeaheadMatch(list, query, 0, getLabel);
}

// ── Internal helpers ─────────────────────────────────────────────

function normalize(value) {
    return String(value || '')
        .toLowerCase()
        .replace(/^@/, '')
        .replace(/\s+/g, ' ')
        .trim();
}

function labelMatchesQuery(label, query) {
    const normalizedLabel = normalize(label);
    const normalizedQuery = normalize(query);
    if (!normalizedQuery) return false;
    return normalizedLabel.startsWith(normalizedQuery) || normalizedLabel.includes(normalizedQuery);
}

function rotatedIndices(length, startIndex) {
    const size = Math.max(0, Number(length) || 0);
    if (size <= 0) return [];
    const start = Number.isInteger(startIndex) ? startIndex : 0;
    const normalizedStart = ((start % size) + size) % size;
    const out = [];
    for (let i = 0; i < size; i++) {
        out.push((normalizedStart + i) % size);
    }
    return out;
}
