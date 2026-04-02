/**
 * pane-detach-transfer.js — Transfer parameters for pane detachment.
 *
 * Generates unique IDs for panes and creates/reads URL parameters
 * for transferring pane identity between windows.
 *
 * Ported from Piclaw runtime/web/src/panes/pane-detach-transfer.ts
 */

function normalizeText(value) {
    return typeof value === 'string' && value.trim() ? value.trim() : null;
}

/**
 * Generate a unique pane detach identifier.
 *
 * @param {string} [prefix='pane']
 * @returns {string}
 */
export function generatePaneDetachId(prefix = 'pane') {
    try {
        if (typeof globalThis?.crypto?.randomUUID === 'function') {
            return `${prefix}-${globalThis.crypto.randomUUID()}`;
        }
    } catch {
        // fall through
    }
    return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Create URL search parameters for a pane detach transfer.
 *
 * @param {{ paneInstanceId: string, paneWindowId: string, paneSourceWindowId?: string|null }} input
 * @returns {Record<string, string>}
 */
export function createPaneDetachTransferParams(input) {
    const paneInstanceId = normalizeText(input?.paneInstanceId);
    const paneWindowId = normalizeText(input?.paneWindowId);
    if (!paneInstanceId || !paneWindowId) return {};

    const paneSourceWindowId = normalizeText(input?.paneSourceWindowId);
    return {
        pane_instance_id: paneInstanceId,
        pane_window_id: paneWindowId,
        ...(paneSourceWindowId ? { pane_source_window_id: paneSourceWindowId } : {}),
    };
}

/**
 * Read pane detach transfer state from URL search parameters.
 *
 * @param {{ search?: string|null, panePath?: string|null, paneLabel?: string|null }} [options]
 * @returns {{ panePath: string|null, paneLabel: string|null, paneInstanceId: string|null, paneWindowId: string|null, paneSourceWindowId: string|null }}
 */
export function readPaneDetachTransferState(options = {}) {
    const params = new URLSearchParams(options.search || '');
    return {
        panePath: normalizeText(params.get('pane_path')) || normalizeText(options.panePath),
        paneLabel: normalizeText(params.get('pane_label')) || normalizeText(options.paneLabel),
        paneInstanceId: normalizeText(params.get('pane_instance_id')),
        paneWindowId: normalizeText(params.get('pane_window_id')),
        paneSourceWindowId: normalizeText(params.get('pane_source_window_id')),
    };
}

/**
 * Check whether a transfer state has enough data for a detach handshake.
 *
 * @param {{ panePath?: string|null, paneInstanceId?: string|null, paneWindowId?: string|null }|null} state
 * @returns {boolean}
 */
export function hasPaneDetachTransferState(state) {
    return Boolean(state?.panePath && state?.paneInstanceId && state?.paneWindowId);
}
