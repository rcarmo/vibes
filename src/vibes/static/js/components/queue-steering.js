// A successful steering submission is single-use for its chat/turn/row identity,
// not just while the HTTP request is in flight. Rejected requests remain retryable.
export function createQueueSteeringGuard() {
    const chats = new Map();
    return {
        async run(chatId, turnId, rowId, submit) {
            if (!chatId || !turnId || rowId == null) return false;
            let entry = chats.get(chatId);
            if (!entry || entry.turnId !== turnId) {
                entry = { turnId, rows: new Set() };
                chats.set(chatId, entry);
            }
            if (entry.rows.has(rowId)) return false;
            entry.rows.add(rowId);
            try {
                await submit();
                return true;
            } catch (error) {
                // Captured entry: an old failure cannot unlock a newer turn's row.
                entry.rows.delete(rowId);
                throw error;
            }
        },
    };
}
