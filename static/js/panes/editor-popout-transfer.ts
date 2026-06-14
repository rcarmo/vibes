/**
 * Editor state transfer for pop-out windows.
 *
 * Stashes editor content, cursor/scroll position, and pane override IDs
 * into localStorage with a 5-minute TTL. A receiving window consumes
 * the token from the URL, restores state, and cleans up the URL.
 */

const EDITOR_POPOUT_STATE_PREFIX = 'vibes:editor-popout:';
export const EDITOR_POPOUT_STATE_TTL_MS = 5 * 60 * 1000;

export interface EditorViewState {
    cursorLine?: number;
    cursorCol?: number;
    scrollTop?: number;
}

export interface EditorPopoutState {
    path: string;
    content?: string;
    mtime?: string | null;
    paneOverrideId?: string | null;
    viewState?: EditorViewState | null;
    capturedAt?: number;
}

interface StorageLike {
    getItem(key: string): string | null;
    setItem(key: string, value: string): void;
    removeItem(key: string): void;
}

interface RuntimeLike {
    localStorage?: StorageLike;
    window?: RuntimeWindowLike;
    location?: Location;
    history?: History;
    document?: Document;
}

type RuntimeWindowLike = RuntimeLike;

function getStorage(runtime: RuntimeLike | typeof globalThis | null | undefined): StorageLike | null {
    try {
        return (runtime as RuntimeLike | undefined)?.localStorage ?? null;
    } catch {
        return null;
    }
}

function createToken(nowMs = Date.now()): string {
    return `editor-popout-${nowMs.toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function normalizePath(value: unknown): string {
    return typeof value === 'string' ? value.trim() : '';
}

function normalizeOverrideId(value: unknown): string | null {
    const normalized = typeof value === 'string' ? value.trim() : '';
    return normalized || null;
}

function normalizeContent(value: unknown): string | undefined {
    return typeof value === 'string' ? value : undefined;
}

function normalizeMtime(value: unknown): string | null | undefined {
    if (value === undefined) return undefined;
    if (typeof value !== 'string') return null;
    const normalized = value.trim();
    return normalized || null;
}

function normalizeViewState(value: unknown): EditorViewState | null {
    if (!value || typeof value !== 'object') return null;
    const input = value as Partial<EditorViewState>;
    const next: EditorViewState = {};
    if (typeof input.cursorLine === 'number' && Number.isFinite(input.cursorLine)) next.cursorLine = input.cursorLine;
    if (typeof input.cursorCol === 'number' && Number.isFinite(input.cursorCol)) next.cursorCol = input.cursorCol;
    if (typeof input.scrollTop === 'number' && Number.isFinite(input.scrollTop)) next.scrollTop = input.scrollTop;
    return Object.keys(next).length > 0 ? next : null;
}

/**
 * Consume a one-shot transfer token from the current URL and clean
 * the parameter from the address bar.
 */
export function consumePanePopoutTransferToken(paramName: string, runtime: RuntimeLike | typeof globalThis = globalThis): string | null {
    const win = (runtime as RuntimeLike)?.window ?? (runtime as RuntimeLike);
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
 */
export function stashEditorPopoutState(state: Partial<EditorPopoutState> | null | undefined, runtime: RuntimeLike | typeof globalThis = globalThis, nowMs = Date.now()): string | null {
    const storage = getStorage(runtime);
    const path = normalizePath(state?.path);
    if (!storage || !path) return null;

    const payload: EditorPopoutState = {
        path,
        content: normalizeContent(state?.content),
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
 */
export function consumeEditorPopoutState(token: unknown, runtime: RuntimeLike | typeof globalThis = globalThis, nowMs = Date.now()): EditorPopoutState | null {
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
        const parsed = JSON.parse(raw) as Partial<EditorPopoutState> | null;
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
 */
export function createEditorPopoutTransferPayload(state: Partial<EditorPopoutState> | null | undefined, runtime: RuntimeLike | typeof globalThis = globalThis, nowMs = Date.now()): Record<string, string> | null {
    const token = stashEditorPopoutState(state, runtime, nowMs);
    return token ? { editor_popout: token } : null;
}
