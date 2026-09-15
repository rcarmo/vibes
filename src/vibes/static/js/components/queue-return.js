// Adapted from Tau's shared queue-return flow. MIT: ../../vendor/licenses/PICLAW-MIT.txt
export function preserveQueuedRecovery(storage, { sessionId, queueId, text }) {
    if (!sessionId || queueId === undefined || queueId === null) throw new Error('Queue recovery identity required');
    const key = `vibes_queue_return:${encodeURIComponent(sessionId)}:${encodeURIComponent(queueId)}`;
    const value = JSON.stringify({ sessionId, queueId, text });
    storage.setItem(key, value);
    if (storage.getItem(key) !== value) throw new Error('Could not verify queue recovery copy');
    return key;
}

export function recoverQueuedDraft(storage, key, sessionId) {
    const recovery = JSON.parse(storage.getItem(key) || 'null');
    if (!recovery || recovery.sessionId !== sessionId || typeof recovery.text !== 'string') throw new Error('Invalid queue recovery');
    const draftKey = `vibes_compose_draft:${encodeURIComponent(sessionId)}`;
    const raw = storage.getItem(draftKey);
    const draft = raw ? JSON.parse(raw) : {};
    if (!draft || typeof draft !== 'object' || Array.isArray(draft)) throw new Error('Invalid existing draft');
    const applied = Array.isArray(draft.queueRecoveries) ? draft.queueRecoveries.filter(value => typeof value === 'string') : [];
    const existing = typeof draft.text === 'string' ? draft.text : '';
    if (applied.includes(key)) { storage.removeItem(key); return existing; }
    const text = existing ? `${existing}\n\n${recovery.text}` : recovery.text;
    if (text.length > 100000) throw new Error('Combined draft exceeds composer limit; recovery retained');
    const value = JSON.stringify({ ...draft, text, queueRecoveries: [...applied, key] });
    storage.setItem(draftKey, value);
    if (storage.getItem(draftKey) !== value) throw new Error('Could not verify restored draft; recovery retained');
    storage.removeItem(key);
    return text;
}

export async function returnQueuedText({ text, preserve, remove }) {
    if (typeof text !== 'string' || !text.trim()) throw new Error('Queued message has no editable text');
    await preserve(text);
    if (!await remove()) return { removed: false, preserved: true };
    return { removed: true, preserved: true };
}
