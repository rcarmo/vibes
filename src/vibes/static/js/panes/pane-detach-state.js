/**
 * pane-detach-state.js — Pane ownership state management.
 *
 * Tracks which window owns a detached pane, supports pending ownership
 * claims during the handshake phase, and verifies claim matching.
 *
 * Ported from Piclaw runtime/web/src/panes/pane-detach-state.ts
 */

function normalizeText(value) {
    return typeof value === 'string' && value.trim() ? value.trim() : null;
}

/**
 * Create a pending pane ownership state for the handshake phase.
 *
 * @param {{ panePath: string, paneInstanceId: string, ownerWindowId: string, label?: string|null, sourceWindowId?: string|null, now?: string }} input
 * @returns {{ panePath: string, paneInstanceId: string, ownerWindowId: string, detachedAt: string, requestedAt: string, label: string|null, sourceWindowId: string|null }|null}
 */
export function createPendingPaneOwnershipState(input) {
    const panePath = normalizeText(input?.panePath);
    const paneInstanceId = normalizeText(input?.paneInstanceId);
    const ownerWindowId = normalizeText(input?.ownerWindowId);
    if (!panePath || !paneInstanceId || !ownerWindowId) return null;

    const timestamp = normalizeText(input?.now) || new Date().toISOString();
    return {
        panePath,
        paneInstanceId,
        ownerWindowId,
        detachedAt: timestamp,
        requestedAt: timestamp,
        label: normalizeText(input?.label),
        sourceWindowId: normalizeText(input?.sourceWindowId),
    };
}

/**
 * Check whether a detach claim matches a pending ownership state.
 *
 * @param {{ panePath: string, paneInstanceId: string, ownerWindowId: string }|null} pending
 * @param {{ panePath?: string|null, paneInstanceId?: string|null, paneWindowId?: string|null }|null} claim
 * @returns {boolean}
 */
export function matchesPaneDetachClaim(pending, claim) {
    if (!pending || !claim) return false;
    return normalizeText(claim.panePath) === pending.panePath
        && normalizeText(claim.paneInstanceId) === pending.paneInstanceId
        && normalizeText(claim.paneWindowId) === pending.ownerWindowId;
}

/**
 * Finalize a pending ownership state into a confirmed ownership record.
 *
 * @param {{ panePath: string, paneInstanceId: string, ownerWindowId: string, label?: string|null }|null} pending
 * @param {string|null} [now]
 * @returns {{ panePath: string, paneInstanceId: string, ownerWindowId: string, detachedAt: string, label: string|null }|null}
 */
export function finalizePendingPaneOwnership(pending, now) {
    if (!pending) return null;
    return {
        panePath: pending.panePath,
        paneInstanceId: pending.paneInstanceId,
        ownerWindowId: pending.ownerWindowId,
        detachedAt: normalizeText(now) || new Date().toISOString(),
        label: pending.label || null,
    };
}
