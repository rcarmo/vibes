/**
 * editor-popout-transfer.js — Editor state transfer for pop-out windows.
 *
 * Stashes editor content, cursor/scroll position, and pane override IDs
 * into localStorage with a 5-minute TTL.  A receiving window consumes
 * the token from the URL, restores state, and cleans up the URL.
 *
 * Ported from Piclaw runtime/web/src/panes/editor-popout-transfer.ts
 */

const EDITOR_POPOUT_STATE_PREFIX = 'vibes:editor-popout:';
const EDITOR_POPOUT_STATE_TTL_MS = 5 * 60 * 1000;

function getStorage(runtime) {
    try {
        return runtime?.localStorage ?? null;
    } catch {
        return null;
    }
}

function createToken(nowMs = Date.now()) {
    return `editor-popout-${nowMs.toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function normalizePath(value) {
    return typeof value === 'string' ? value.trim() : '';
}

function normalizeOverrideId(value) {
    const normalized = typeof value === 'string' ? value.trim() : '';
    return normalized || null;
}

function normalizeContent(value) {
    return typeof value === 'string' ? value : undefined;
}

function normalizeMtime(value) {
    if (value === undefined) return undefined;
    if (typeof value !== 'string') return null;
    const normalized = value.trim();
    return normalized || null;
}

function normalizeViewState(value) {
    if (!value || typeof value !== 'object') return null;
    const next = {};
    if (typeof value.cursorLine === 'number' && Number.isFinite(value.cursorLine)) next.cursorLine = value.cursorLine;
    if (typeof value.cursorCol === 'number' && Number.isFinite(value.cursorCol)) next.cursorCol = value.cursorCol;
    if (typeof value.scrollTop === 'number' && Number.isFinite(value.scrollTop)) next.scrollTop = value.scrollTop;
    return Object.keys(next).length > 0 ? next : null;
}

/**
 * Consume a one-shot transfer token from the current URL and clean
 * the parameter from the address bar.
 *
 * @param {string} paramName - URL search parameter name to read.
 * @param {object} [runtime=globalThis] - Runtime window object.
 * @returns {string|null} The token value, or null if not present.
 */
export function consumePanePopoutTransferToken(paramName, runtime = globalThis) {
    const win = runtime?.window ?? runtime;
    if (!win?.location?.href) return null;
    try {
        const url = new URL(win.location.href);
        const token = url.searchParams.get(paramName)?.trim() || '';
        if (!token) return null;
        url.searchParams.delete(paramName);
        win.history?.replaceState?.(win.history.state, win.document?.title || '', url.toString());
        return token;
    } catch {
        return null;
    }
}

/**
 * Stash editor state into localStorage and return a transfer token.
 *
 * @param {{ path: string, content?: string, mtime?: string|null, paneOverrideId?: string|null, viewState?: object|null }} state
 * @param {object} [runtime=globalThis]
 * @param {number} [nowMs=Date.now()]
 * @returns {string|null} Transfer token, or null on failure.
 */
export function stashEditorPopoutState(state, runtime = globalThis, nowMs = Date.now()) {
    const storage = getStorage(runtime);
    const path = normalizePath(state?.path);
    if (!storage || !path) return null;

    const payload = {
        path,
        content: normalizeContent(state?.content),
        savedContent: normalizeContent(state?.savedContent),
        mtime: normalizeMtime(state?.mtime),
        paneOverrideId: normalizeOverrideId(state?.paneOverrideId),
        viewState: normalizeViewState(state?.viewState),
        capturedAt: nowMs,
    };

    const hasTransferData = Boolean(
        payload.content !== undefined
            || payload.paneOverrideId
            || payload.viewState
            || payload.mtime,
    );
    if (!hasTransferData) return null;

    const token = createToken(nowMs);
    try {
        storage.setItem(`${EDITOR_POPOUT_STATE_PREFIX}${token}`, JSON.stringify(payload));
        return token;
    } catch {
        return null;
    }
}

/**
 * Consume stashed editor state from localStorage (one-shot).
 *
 * @param {string} [token]
 * @param {object} [runtime=globalThis]
 * @param {number} [nowMs=Date.now()]
 * @returns {{ path: string, content?: string, mtime?: string|null, paneOverrideId?: string|null, viewState?: object|null, capturedAt?: number }|null}
 */
export function consumeEditorPopoutState(token, runtime = globalThis, nowMs = Date.now()) {
    const normalizedToken = typeof token === 'string' ? token.trim() : '';
    const storage = getStorage(runtime);
    if (!normalizedToken || !storage) return null;

    const key = `${EDITOR_POPOUT_STATE_PREFIX}${normalizedToken}`;
    let raw = '';
    try {
        raw = storage.getItem(key) || '';
    } catch {
        return null;
    }
    if (!raw) return null;

    try {
        storage.removeItem(key);
    } catch {
        /* one-shot transfer cleanup is best-effort */
    }

    try {
        const parsed = JSON.parse(raw);
        const capturedAt = typeof parsed?.capturedAt === 'number' && Number.isFinite(parsed.capturedAt)
            ? parsed.capturedAt
            : nowMs;
        if (capturedAt + EDITOR_POPOUT_STATE_TTL_MS < nowMs) {
            return null;
        }

        const path = normalizePath(parsed?.path);
        if (!path) return null;

        return {
            path,
            content: normalizeContent(parsed?.content),
            savedContent: normalizeContent(parsed?.savedContent),
            mtime: normalizeMtime(parsed?.mtime),
            paneOverrideId: normalizeOverrideId(parsed?.paneOverrideId),
            viewState: normalizeViewState(parsed?.viewState),
            capturedAt,
        };
    } catch {
        return null;
    }
}

/**
 * Stash editor state and return query parameters for the popout URL.
 *
 * @param {{ path: string, content?: string, mtime?: string|null, paneOverrideId?: string|null, viewState?: object|null }} state
 * @param {object} [runtime=globalThis]
 * @param {number} [nowMs=Date.now()]
 * @returns {Record<string, string>|null}
 */
export function createEditorPopoutTransferPayload(state, runtime = globalThis, nowMs = Date.now()) {
    const token = stashEditorPopoutState(state, runtime, nowMs);
    return token ? { editor_popout: token } : null;
}
